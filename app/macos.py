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
            appkit_mod: Any = AppKit
            for monitor in _MACOS_MONITORS:
                try:
                    appkit_mod.NSEvent.removeMonitor_(monitor)
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
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]
    from webview.platforms.cocoa import BrowserView  # type: ignore[import-not-found]

    appkit_mod: Any = AppKit
    webkit_mod: Any = WebKit
    objc_mod: Any = objc

    browser_view = BrowserView.instances.get(window.uid)
    if browser_view is None:
        raise RuntimeError("Unable to locate the native WKWebView instance.")
    webview = browser_view.webview
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
            request = action.request()
            destination = str(request.URL().absoluteString() or "")
            http_method = str(request.HTTPMethod() or "GET").upper()
            original_headers = dict(request.allHTTPHeaderFields() or {})
            has_wrapper = "X-Wrapper-Version" in original_headers
            has_handled = "X-Handled" in original_headers
            logger.debug(
                "NavigationDelegate: %s %s | has_wrapper=%s has_handled=%s allowed=%s headers=%s",
                http_method, destination[:120], has_wrapper, has_handled,
                (not destination or is_navigation_allowed(destination, config)),
                list(original_headers.keys()),
            )
            if not destination or is_navigation_allowed(destination, config):
                # Inject X-Wrapper-Version on GET requests that don't have it yet.
                # NEVER intercept POST — WebKit returns None for HTTPBody() in
                # navigation policy decisions, so rebuilding strips the form
                # body (CSRF _token) causing 419 Session Expired.
                if (
                    config.wrapper_version
                    and http_method == "GET"
                    and not has_wrapper
                    and not has_handled
                    and str(request.URL()) != "about:blank"
                ):
                    try:
                        import Foundation as foundation_mod  # type: ignore[import-not-found]
                        url = request.URL()
                        new_request = foundation_mod.NSMutableURLRequest.requestWithURL_(url)  # type: ignore[attr-defined]
                        new_request.setHTTPMethod_("GET")
                        # Copy all original headers + add ours
                        new_headers = dict(original_headers)
                        new_headers["X-Wrapper-Version"] = config.wrapper_version
                        new_headers["X-Handled"] = "true"
                        new_request.setAllHTTPHeaderFields_(
                            AppKit.NSDictionary({k: str(v) for k, v in new_headers.items()})  # type: ignore[attr-defined]
                        )
                        new_request.setHTTPShouldHandleCookies_(request.HTTPShouldHandleCookies())
                        # Cancel original, load new GET request with header
                        logger.debug("NavigationDelegate: CANCEL+RELOAD %s with X-Wrapper-Version", destination[:120])
                        handler(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
                        wk_webview.loadRequest_(new_request)
                        return
                    except Exception as e:
                        logger.debug(
                            "Failed to inject X-Wrapper-Version in NavigationDelegate: %s", e
                        )
                        # Fall through to allow original request

                # Allow: already has header, POST, about:blank, or injection failed
                logger.debug("NavigationDelegate: ALLOW (forwarding to delegate) %s %s", http_method, destination[:120])
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
            error_code = None
            try:
                code_attr = getattr(error, "code", None)
                error_code = code_attr() if callable(code_attr) else code_attr
            except Exception:
                pass
            logger.debug("webView_didFailProvisionalNavigation: error_code=%s (%s)", error_code, error)
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
                    import Foundation  # type: ignore[import-not-found]
                    foundation_mod: Any = Foundation
                    ns_url = foundation_mod.NSURL.URLWithString_(config.web_app_url)
                    req = foundation_mod.NSURLRequest.requestWithURL_(ns_url)
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

    monitor = appkit_mod.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        appkit_mod.NSEventMaskKeyDown,
        shortcut_monitor,
    )

    with _MACOS_LOCK:
        _MACOS_DELEGATES.append(delegate)
        _MACOS_MONITORS.append(monitor)
