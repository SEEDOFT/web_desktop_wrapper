from __future__ import annotations

import threading
import webbrowser
from types import MethodType
from typing import Any
from urllib.parse import urlparse

from app.config import AppConfig
from app.logger import get_logger
from app.navigation import is_external_url_allowed, is_navigation_allowed

logger = get_logger(__name__)

_MACOS_DELEGATES: dict[str, Any] = {}
_MACOS_MONITORS: dict[str, Any] = {}
_MACOS_PENDING: set[str] = set()
_MACOS_LOADERS: dict[str, tuple[Any, Any]] = {}
_MACOS_LOCK = threading.Lock()


class _DecisionHandlerOnce:
    """Ensure a WKNavigationDelegate policy callback is completed at most once."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.called = False

    def __call__(self, policy: Any) -> None:
        if self.called:
            logger.warning("Ignoring duplicate macOS navigation policy decision")
            return
        self.called = True
        self._handler(policy)


def cleanup_macos_handlers() -> None:
    """Clean up macOS event monitors and delegate references."""
    try:
        import Foundation
        from PyObjCTools import AppHelper
        foundation_mod: Any = Foundation
        if not foundation_mod.NSThread.isMainThread():
            AppHelper.callAfter(cleanup_macos_handlers)
            return
    except ImportError:
        pass
    with _MACOS_LOCK:
        try:
            import AppKit  # type: ignore[import-not-found]
            appkit_mod: Any = AppKit
            for monitor in _MACOS_MONITORS.values():
                try:
                    appkit_mod.NSEvent.removeMonitor_(monitor)
                except Exception as e:
                    logger.debug("Failed to remove macOS monitor: %s", e)
        except Exception:
            pass
        _MACOS_MONITORS.clear()
        _MACOS_DELEGATES.clear()
        _MACOS_PENDING.clear()
        for browser_view, original_loader in _MACOS_LOADERS.values():
            try:
                browser_view.load_url = original_loader
            except Exception as e:
                logger.debug("Failed to restore macOS URL loader: %s", e)
        _MACOS_LOADERS.clear()
    logger.debug("Cleaned up macOS native delegates and monitors")


def _install_versioned_url_loader(
    browser_view: Any,
    config: AppConfig,
    foundation: Any,
    app_helper: Any,
) -> bool:
    """Attach the version header to wrapper-initiated approved URL loads."""
    handler_key = str(browser_view.pywebview_window.uid)
    with _MACOS_LOCK:
        if handler_key in _MACOS_LOADERS:
            return True

    original_loader = browser_view.load_url

    def load_url(instance: Any, url: str) -> None:
        parsed = urlparse(url)
        if (
            not config.wrapper_version
            or parsed.scheme.lower() not in {"http", "https"}
            or not is_navigation_allowed(url, config)
        ):
            original_loader(url)
            return

        def load() -> None:
            page_url = foundation.NSURL.URLWithString_(instance.quote(url))
            request = foundation.NSMutableURLRequest.requestWithURL_(page_url)
            request.setValue_forHTTPHeaderField_(
                config.wrapper_version,
                "X-Wrapper-Version",
            )
            instance.webview.loadRequest_(request)

        instance.url = url
        app_helper.callAfter(load)

    browser_view.load_url = MethodType(load_url, browser_view)
    with _MACOS_LOCK:
        _MACOS_LOADERS[handler_key] = (browser_view, original_loader)
    logger.info(
        "macOS initial request header configured for wrapper version %s",
        config.wrapper_version,
    )
    return True


def _copy_request_with_version_header(request: Any, version: str) -> Any:
    """Preserve a native request and change only its wrapper version header."""
    mutable_request = request.mutableCopy()
    mutable_request.setValue_forHTTPHeaderField_(version, "X-Wrapper-Version")
    return mutable_request


def _versioned_main_frame_request(action: Any, config: AppConfig) -> Any:
    """Never replay a child frame or popup into the main WKWebView."""
    frame = action.targetFrame()
    if frame is None or not frame.isMainFrame():
        return None
    request = action.request()
    destination = str(request.URL().absoluteString() or "")
    if (not config.wrapper_version or urlparse(destination).scheme.lower() not in {"http", "https"}
        or not is_navigation_allowed(destination, config)):
        return None
    headers = dict(request.allHTTPHeaderFields() or {})
    versions = [str(value) for name, value in headers.items() if str(name).lower() == "x-wrapper-version"]
    if versions and all(value == config.wrapper_version for value in versions):
        return None
    return _copy_request_with_version_header(request, config.wrapper_version)


def _complete_navigation_progress(webview: Any, *, failed: bool = False) -> None:
    method = "cancel" if failed else "finish"
    try:
        webview.evaluateJavaScript_completionHandler_(
            f"window.__wdwNavigationProgress && window.__wdwNavigationProgress.{method}()", None
        )
    except Exception:
        logger.debug("Unable to complete navigation progress")


def configure_macos_webview(window: Any, config: AppConfig) -> None:
    """Install an allowlisting WKNavigationDelegate and keyboard shortcuts."""
    import AppKit  # type: ignore[import-not-found]
    import Foundation  # type: ignore[import-not-found]
    import objc  # type: ignore[import-not-found]
    import WebKit  # type: ignore[import-not-found]
    from Foundation import NSObject, NSThread  # type: ignore[import-not-found]
    from PyObjCTools import AppHelper  # type: ignore[import-not-found]
    from webview.platforms.cocoa import BrowserView  # type: ignore[import-not-found]

    appkit_mod: Any = AppKit
    webkit_mod: Any = WebKit

    handler_key = str(window.uid)
    if not NSThread.isMainThread():
        with _MACOS_LOCK:
            if handler_key in _MACOS_PENDING or handler_key in _MACOS_DELEGATES:
                return
            _MACOS_PENDING.add(handler_key)

        def configure_on_main_thread() -> None:
            with _MACOS_LOCK:
                _MACOS_PENDING.discard(handler_key)
            configure_macos_webview(window, config)

        AppHelper.callAfter(configure_on_main_thread)
        return

    browser_view = BrowserView.instances.get(window.uid)
    if browser_view is None:
        raise RuntimeError("Unable to locate the native WKWebView instance.")
    webview = browser_view.webview
    _install_versioned_url_loader(browser_view, config, Foundation, AppHelper)
    with _MACOS_LOCK:
        if handler_key in _MACOS_DELEGATES:
            logger.debug("macOS handlers already configured for window %s", handler_key)
            return
    original_delegate = webview.navigationDelegate()

    class NavigationDelegate(NSObject):
        def initWithDelegate_(self, delegate: Any) -> Any:
            self = objc.super(NavigationDelegate, self).init()  # type: ignore[attr-defined]
            if self is None:
                return None
            self._delegate = delegate
            return self

        def forwardingTargetForSelector_(self, selector: Any) -> Any:
            return self._delegate

        def respondsToSelector_(self, selector: Any) -> bool:
            return bool(
                objc.super(NavigationDelegate, self).respondsToSelector_(selector)  # type: ignore[attr-defined]
                or (self._delegate and self._delegate.respondsToSelector_(selector))
            )

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self,
            wk_webview: Any,
            action: Any,
            handler: Any,
        ) -> None:
            decision = _DecisionHandlerOnce(handler)
            allow_policy = getattr(WebKit, "WKNavigationActionPolicyAllow", 1)
            try:
                request = action.request()
                destination = str(request.URL().absoluteString() or "")
                http_method = str(request.HTTPMethod() or "GET").upper()
                original_headers = dict(request.allHTTPHeaderFields() or {})
                allowed = not destination or is_navigation_allowed(destination, config)
                logger.debug(
                    "NavigationDelegate: method=%s allowed=%s headers=%s body=%s stream=%s",
                    http_method,
                    allowed,
                    list(original_headers.keys()),
                    request.HTTPBody() is not None,
                    request.HTTPBodyStream() is not None,
                )
                if allowed:
                    frame = action.targetFrame()
                    if frame is not None and frame.isMainFrame() and urlparse(destination).scheme.lower() in {"http", "https"}:
                        window._wdw_retry_url = destination if http_method == "GET" else config.web_app_url
                    mutable_request = _versioned_main_frame_request(action, config)
                    if mutable_request is not None:
                        decision(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
                        wk_webview.loadRequest_(mutable_request)
                        return
                    logger.debug(
                        "NavigationDelegate: forwarding allowed %s navigation",
                        http_method,
                    )
                    if self._delegate and hasattr(
                        self._delegate,
                        "webView_decidePolicyForNavigationAction_decisionHandler_",
                    ):
                        self._delegate.webView_decidePolicyForNavigationAction_decisionHandler_(
                            wk_webview,
                            action,
                            decision,
                        )
                    else:
                        decision(allow_policy)
                    return

                decision(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
                _complete_navigation_progress(wk_webview, failed=True)
                if (
                    config.open_external_links
                    and is_external_url_allowed(destination, config)
                ):
                    webbrowser.open(destination, new=2)
            except Exception:
                logger.exception("macOS navigation policy evaluation failed")
                decision(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
                _complete_navigation_progress(wk_webview, failed=True)

        def webView_didFinishNavigation_(self, wk_webview: Any, navigation: Any) -> None:
            _complete_navigation_progress(wk_webview)
            if self._delegate and hasattr(self._delegate, "webView_didFinishNavigation_"):
                self._delegate.webView_didFinishNavigation_(wk_webview, navigation)

        def webView_didFailProvisionalNavigation_withError_(
            self,
            wk_webview: Any,
            navigation: Any,
            error: Any,
        ) -> None:
            error_code = None
            try:
                code_attr = getattr(error, "code", None)
                error_code = code_attr() if callable(code_attr) else code_attr
            except Exception:
                pass
            logger.debug("webView_didFailProvisionalNavigation: error_code=%s (%s)", error_code, error)
            if error_code != 102:
                _complete_navigation_progress(wk_webview, failed=True)
            # -999 is NSURLErrorCancelled, 102 is WebKitErrorFrameLoadInterruptedByPolicyChange
            if error_code not in (-999, 102) and error_code is not None:
                from app.browser import _safe_error_html
                error_html = _safe_error_html(
                    config,
                    "The application could not be reached. Check your connection and try again.",
                )
                wk_webview.loadHTMLString_baseURL_(error_html, None)

            if self._delegate and hasattr(
                self._delegate,
                "webView_didFailProvisionalNavigation_withError_",
            ):
                self._delegate.webView_didFailProvisionalNavigation_withError_(
                    wk_webview,
                    navigation,
                    error,
                )

        def webView_didFailNavigation_withError_(
            self,
            wk_webview: Any,
            navigation: Any,
            error: Any,
        ) -> None:
            error_code = None
            try:
                code_attr = getattr(error, "code", None)
                error_code = code_attr() if callable(code_attr) else code_attr
            except Exception:
                pass
            logger.debug("webView_didFailNavigation: error_code=%s (%s)", error_code, error)
            if error_code != 102:
                _complete_navigation_progress(wk_webview, failed=True)
            if error_code not in (-999, 102) and error_code is not None:
                from app.browser import _safe_error_html
                error_html = _safe_error_html(
                    config,
                    "The application could not be reached. Check your connection and try again.",
                )
                wk_webview.loadHTMLString_baseURL_(error_html, None)

            if self._delegate and hasattr(
                self._delegate,
                "webView_didFailNavigation_withError_",
            ):
                self._delegate.webView_didFailNavigation_withError_(
                    wk_webview,
                    navigation,
                    error,
                )

    delegate = NavigationDelegate.alloc().initWithDelegate_(original_delegate)
    webview.setNavigationDelegate_(delegate)

    if config.wrapper_version and hasattr(webview, "setCustomUserAgent_"):
        try:
            current_ua = str(webview.customUserAgent() or "")
            if not current_ua:
                base_ua = config.user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)"
                webview.setCustomUserAgent_(f"{base_ua} DigiWrapper/{config.wrapper_version}")
            elif f"DigiWrapper/{config.wrapper_version}" not in current_ua:
                webview.setCustomUserAgent_(f"{current_ua} DigiWrapper/{config.wrapper_version}")
        except Exception as e:
            logger.debug("Failed to set customUserAgent with wrapper version on macOS: %s", e)

    if config.wrapper_version and hasattr(webview, "configuration"):
        try:
            from app.scripts_loader import get_script
            header_script = get_script(
                "wrapper_version_header.js",
                WRAPPER_VERSION=config.wrapper_version,
            )
            header_script += "\n" + get_script("navigation_progress.js")
            if header_script:
                user_script = webkit_mod.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                    header_script,
                    getattr(WebKit, "WKUserScriptInjectionTimeAtDocumentStart", 0),
                    False,
                )
                webview.configuration().userContentController().addUserScript_(user_script)
        except Exception as e:
            logger.debug("Failed to inject X-Wrapper-Version script on macOS: %s", e)

    def shortcut_monitor(event: Any) -> Any:
        flags = event.modifierFlags()
        if not (flags & appkit_mod.NSEventModifierFlagCommand):
            return event

        chars = str(event.charactersIgnoringModifiers() or "").lower()
        shift = bool(flags & appkit_mod.NSEventModifierFlagShift)

        if chars == "r":
            url_obj = getattr(webview, "URL", lambda: None)()
            url_str = str(getattr(url_obj, "absoluteString", lambda: "")() or "").lower() if url_obj else ""
            is_error_or_blank = not url_str or url_str in {"about:blank", ""} or url_str.startswith("data:")

            if is_error_or_blank and config.web_app_url:
                try:
                    browser_view.load_url(getattr(window, "_wdw_retry_url", config.web_app_url))
                except Exception as e:
                    logger.debug("Failed to navigate to web_app_url on Cmd+R: %s", e)
            else:
                if shift and hasattr(webview, "reloadFromOrigin"):
                    webview.reloadFromOrigin()
                else:
                    webview.reload()
            return None

        if chars in {"=", "+"}:
            if hasattr(webview, "pageZoom"):
                webview.setPageZoom_(webview.pageZoom() * 1.15)
            return None

        if chars == "-":
            if hasattr(webview, "pageZoom"):
                webview.setPageZoom_(max(0.3, webview.pageZoom() / 1.15))
            return None

        if chars == "0":
            if hasattr(webview, "setPageZoom_"):
                webview.setPageZoom_(1.0)
            return None

        if chars == "w":
            try:
                window.destroy()
            except Exception as e:
                logger.debug("Failed to destroy window on Cmd+W: %s", e)
            return None

        if chars == "f" and hasattr(webview, "performTextFinderAction_"):
            webview.performTextFinderAction_(1)
            return None

        if chars == "p":
            try:
                webview.printOperation().runOperation()
            except Exception as e:
                logger.debug("Failed to run print operation: %s", e)
            return None

        return event

    monitor = appkit_mod.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        appkit_mod.NSEventMaskKeyDown,
        shortcut_monitor,
    )

    with _MACOS_LOCK:
        _MACOS_DELEGATES[handler_key] = delegate
        _MACOS_MONITORS[handler_key] = monitor
