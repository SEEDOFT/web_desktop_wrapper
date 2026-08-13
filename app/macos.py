from __future__ import annotations

import webbrowser
from typing import Any

from app.config import AppConfig
from app.navigation import is_navigation_allowed


_MACOS_DELEGATES: list[Any] = []


def configure_macos_webview(window: Any, config: AppConfig) -> None:
    """Install an allowlisting WKNavigationDelegate around pywebview's delegate."""
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
                or self._delegate.respondsToSelector_(selector)
            )

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self,
            wk_webview: Any,
            action: Any,
            handler: Any,
        ) -> None:
            destination = str(action.request().URL().absoluteString() or "")
            if not destination or is_navigation_allowed(destination, config):
                self._delegate.webView_decidePolicyForNavigationAction_decisionHandler_(
                    wk_webview,
                    action,
                    handler,
                )
                return

            handler(getattr(WebKit, "WKNavigationActionPolicyCancel", 0))
            if config.open_external_links:
                webbrowser.open(destination, new=2)

    delegate = NavigationDelegate.alloc().initWithDelegate_(original_delegate)
    webview.setNavigationDelegate_(delegate)

    def shortcut_monitor(event: Any) -> Any:
        flags = event.modifierFlags()
        if not flags & AppKit.NSCommandKeyMask:
            return event
        key = str(event.charactersIgnoringModifiers() or "").lower()
        if key == "r":
            webview.reload()
            return None
        if key == "f" and hasattr(webview, "performTextFinderAction_"):
            webview.performTextFinderAction_(1)
            return None
        if key == "p":
            webview.printOperation().runOperation()
            return None
        return event

    monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        AppKit.NSEventMaskKeyDown,
        shortcut_monitor,
    )
    _MACOS_DELEGATES.extend((delegate, shortcut_monitor, monitor))
