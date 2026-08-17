from __future__ import annotations

import threading
import webbrowser
from typing import Any

from app.config import AppConfig
from app.logger import get_logger
from app.navigation import is_navigation_allowed

logger = get_logger(__name__)

_MACOS_DELEGATES: list[Any] = []
_MACOS_MONITORS: list[Any] = []
_MACOS_LOCK = threading.Lock()


def cleanup_macos_handlers() -> None:
    """Clean up macOS event monitors and delegate references."""
    with _MACOS_LOCK:
        try:
            import AppKit  # type: ignore[import-not-found]
            for monitor in _MACOS_MONITORS:
                try:
                    AppKit.NSEvent.removeMonitor_(monitor)
                except Exception as e:
                    logger.debug("Failed to remove macOS monitor: %s", e)
        except Exception:
            pass
        _MACOS_MONITORS.clear()
        _MACOS_DELEGATES.clear()
    logger.debug("Cleaned up macOS native delegates and monitors")


def configure_macos_webview(window: Any, config: AppConfig) -> None:
    """Install an allowlisting WKNavigationDelegate and keyboard shortcuts."""
    import AppKit  # type: ignore[import-not-found]
    import WebKit  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]
    from objc import super  # type: ignore[import-not-found]
    from webview.platforms.cocoa import BrowserView  # type: ignore[import-not-found]

    browser_view = BrowserView.instances.get(window.uid)
    if browser_view is None:
        raise RuntimeError("Unable to locate the native WKWebView instance.")
    webview = browser_view.webview
    original_delegate = webview.navigationDelegate()

    class NavigationDelegate(NSObject):
        def initWithDelegate_(self, delegate: Any) -> Any:
            self = super().init()
            if self is None:
                return None
            self._delegate = delegate
            return self

        def forwardingTargetForSelector_(self, selector: Any) -> Any:
            return self._delegate

        def respondsToSelector_(self, selector: Any) -> bool:
            return bool(
                super().respondsToSelector_(selector)
                or (self._delegate and self._delegate.respondsToSelector_(selector))
            )

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self,
            wk_webview: Any,
            action: Any,
            handler: Any,
        ) -> None:
            destination = str(action.request().URL().absoluteString() or "")
            if not destination or is_navigation_allowed(destination, config):
                if self._delegate and hasattr(
                    self._delegate,
                    "webView_decidePolicyForNavigationAction_decisionHandler_",
                ):
                    self._delegate.webView_decidePolicyForNavigationAction_decisionHandler_(
                        wk_webview,
                        action,
                        handler,
                    )
                else:
                    handler(getattr(WebKit, "WKNavigationActionPolicyAllow", 1))
                return

            handler(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
            if config.open_external_links:
                webbrowser.open(destination, new=2)

        def webView_didFailProvisionalNavigation_withError_(
            self,
            wk_webview: Any,
            navigation: Any,
            error: Any,
        ) -> None:
            error_code = getattr(error, "code", lambda: 0)()
            # -999 is NSURLErrorCancelled (user or policy cancelled navigation)
            if error_code != -999:
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
            error_code = getattr(error, "code", lambda: 0)()
            if error_code != -999:
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

    if config.wrapper_version and hasattr(webview, "configuration"):
        try:
            from app.scripts_loader import get_script
            header_script = get_script(
                "wrapper_version_header.js",
                WRAPPER_VERSION=config.wrapper_version,
            )
            if header_script:
                user_script = WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                    header_script,
                    getattr(WebKit, "WKUserScriptInjectionTimeAtDocumentStart", 0),
                    False,
                )
                webview.configuration().userContentController().addUserScript_(user_script)
        except Exception as e:
            logger.debug("Failed to inject X-Wrapper-Version script on macOS: %s", e)

    def shortcut_monitor(event: Any) -> Any:
        flags = event.modifierFlags()
        if not (flags & AppKit.NSEventModifierFlagCommand):
            return event

        chars = str(event.charactersIgnoringModifiers() or "").lower()
        shift = bool(flags & AppKit.NSEventModifierFlagShift)

        if chars == "r":
            url_obj = getattr(webview, "URL", lambda: None)()
            url_str = str(getattr(url_obj, "absoluteString", lambda: "")() or "").lower() if url_obj else ""
            is_error_or_blank = not url_str or url_str in {"about:blank", ""} or url_str.startswith("data:")

            if is_error_or_blank and config.web_app_url:
                try:
                    import Foundation  # type: ignore[import-not-found]
                    ns_url = Foundation.NSURL.URLWithString_(config.web_app_url)
                    req = Foundation.NSURLRequest.requestWithURL_(ns_url)
                    webview.loadRequest_(req)
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

    monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        AppKit.NSEventMaskKeyDown,
        shortcut_monitor,
    )

    with _MACOS_LOCK:
        _MACOS_DELEGATES.append(delegate)
        _MACOS_MONITORS.append(monitor)
