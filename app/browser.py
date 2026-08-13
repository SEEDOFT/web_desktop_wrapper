from __future__ import annotations

import html
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, cast

try:
    from System import EventArgs  # type: ignore
except Exception:  # pragma: no cover - Windows-only import guard
    EventArgs = Any  # type: ignore

import webview

from app.config import AppConfig
from app.navigation import is_navigation_allowed
from app.platform import browser_backend, persistent_storage_path, renderer_name

_NATIVE_HANDLERS: list[Any] = []

_SHORTCUT_LAST_FIRED: dict[str, float] = {}
_SHORTCUT_DEBOUNCE_SECONDS = 0.4

_SWIPE_NAVIGATION_SCRIPT = """
(function () {
    if (window.__wdwSwipeNavigationInstalled) {
        return;
    }
    window.__wdwSwipeNavigationInstalled = true;
    var THRESHOLD = 100;
    var COOLDOWN_MS = 600;
    var lastNavigationAt = 0;
    function postDirection(direction) {
        var webview = window.chrome && window.chrome.webview;
        if (webview && webview.postMessage) {
            webview.postMessage({ type: "horizontalSwipe", direction: direction });
        }
    }
    function onWheel(event) {
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            return;
        }
        if (Math.abs(event.deltaX) < THRESHOLD) {
            return;
        }
        var now = Date.now();
        if (now - lastNavigationAt < COOLDOWN_MS) {
            return;
        }
        lastNavigationAt = now;
        postDirection(event.deltaX > 0 ? "back" : "forward");
    }
    window.addEventListener("wheel", onWheel, true);
})();
"""


def _swipe_action_from_message(message_json: str | None) -> str | None:
    """Map a ``horizontalSwipe`` host message to a navigation action."""
    if not message_json:
        return None
    try:
        payload = json.loads(message_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "horizontalSwipe":
        return None
    direction = payload.get("direction")
    if direction == "back":
        return "back"
    if direction == "forward":
        return "forward"
    return None


def _open_find_dialog(core_webview: Any) -> None:
    """Open WebView2's find-in-page bar (the browser Ctrl+F equivalent).

    Prefers ``OpenFindDialog`` (newer SDKs) and falls back to the ``Find``
    API with the default find dialog on SDKs that only expose ``StartAsync``.
    """
    try:
        open_dialog = getattr(core_webview, "OpenFindDialog", None)
        if callable(open_dialog):
            open_dialog()
            return
    except Exception:
        pass

    try:
        find = getattr(core_webview, "Find", None)
        if find is None or not callable(getattr(find, "StartAsync", None)):
            return
        create_options = getattr(
            getattr(core_webview, "Environment", None),
            "CreateFindOptions",
            None,
        )
        if not callable(create_options):
            return
        options = create_options()
        options.FindTerm = ""
        options.SuppressDefaultFindDialog = False
        find.StartAsync(options)
    except Exception:
        pass


def _shortcut_action(
    key: str | int | None,
    ctrl: bool = False,
    shift: bool = False,
    alt: bool = False,
) -> str | None:
    if key is None:
        return None

    if isinstance(key, int):
        key_map = {
            82: "r",      # R
            116: "f5",    # F5
            187: "=",     # OEM_Plus
            107: "=",     # Numpad Add
            189: "-",     # OEM_Minus
            109: "-",     # Numpad Subtract
            48: "0",      # D0
            96: "0",      # Numpad 0
            70: "f",      # F
            80: "p",      # P
            87: "w",      # W
            36: "home",   # Home
            46: "delete", # Delete
            122: "f11",   # F11
            37: "left",   # Left arrow
            39: "right",  # Right arrow
        }
        normalized_key = key_map.get(key)
    else:
        normalized_key = str(key).lower()

    if normalized_key is None:
        return None

    if alt and normalized_key in {"left", "arrowleft"}:
        return "back"

    if alt and normalized_key in {"right", "arrowright"}:
        return "forward"

    if ctrl and shift and normalized_key in {"r", "f5"}:
        return "hard_reload"

    if ctrl and normalized_key == "r":
        return "reload"

    if normalized_key == "f5":
        return "reload"

    if ctrl and normalized_key == "w":
        return "close"

    if ctrl and shift and normalized_key == "delete":
        return "clear_browsing_data"

    if ctrl and normalized_key == "home":
        return "home"

    if normalized_key == "f11":
        return "fullscreen"

    if ctrl and normalized_key in {"=", "+", "oemplus", "add"}:
        return "zoom_in"

    if ctrl and normalized_key in {"-", "subtract", "oemminus"}:
        return "zoom_out"

    if ctrl and normalized_key == "0":
        return "zoom_reset"

    if ctrl and normalized_key == "f":
        return "find"

    if ctrl and normalized_key == "p":
        return "print"

    return None


def _navigation_toolbar_layout() -> dict[str, str]:
    return {
        "toolbar_dock": "Top",
        "content_panel_dock": "Fill",
        "host_container_dock": "Fill",
    }


def _modifier_state(args: Any) -> tuple[bool, bool, bool]:
    ctrl = bool(getattr(args, "Control", False) or getattr(args, "Ctrl", False))
    shift = bool(getattr(args, "Shift", False))
    alt = bool(getattr(args, "Alt", False))

    try:
        from System.Windows.Forms import Control, Keys  # type: ignore
    except Exception:
        return ctrl, shift, alt

    try:
        modifier_keys = Control.ModifierKeys
        ctrl = ctrl or bool(modifier_keys & Keys.Control)
        shift = shift or bool(modifier_keys & Keys.Shift)
        alt = alt or bool(modifier_keys & Keys.Alt)
    except Exception:
        pass

    return ctrl, shift, alt


def _clear_http_cache(profile: Any) -> Any | None:
    # Clear only the HTTP cache so a reload ignores stale redirects to the
    # login page without dropping session cookies or DOM storage.
    try:
        import System  # type: ignore

        kinds_type = profile.GetType().Assembly.GetType(
            "Microsoft.Web.WebView2.Core.CoreWebView2BrowsingDataKinds"
        )
        if kinds_type is None:
            return None
        cache_kinds = None
        for candidate in ("DiskCache", "CacheStorage"):
            try:
                cache_kinds = System.Enum.Parse(kinds_type, candidate)
                break
            except Exception:
                continue
        if cache_kinds is None:
            return None
        return profile.ClearBrowsingDataAsync(cache_kinds)
    except Exception:
        return None


def _reload_after_cache_clear(
    core_webview: Any,
    invoke_on_ui_thread: Any,
) -> None:
    """Clear only HTTP cache, then reload without deleting auth storage."""
    task = _clear_http_cache(core_webview.Profile)
    if task is None:
        invoke_on_ui_thread(lambda: core_webview.Reload())
        return

    def reload_when_complete() -> None:
        invoke_on_ui_thread(lambda: core_webview.Reload())

    try:
        from System import Action  # type: ignore

        callback = Action(reload_when_complete)
        _NATIVE_HANDLERS.append(callback)
        task.GetAwaiter().OnCompleted(callback)
    except Exception:
        # Older WebView2/pythonnet combinations may not expose an awaiter.
        # A normal reload remains safe and preserves cookies/site storage.
        invoke_on_ui_thread(lambda: core_webview.Reload())


def _storage_path(
    config: AppConfig,
    platform_value: str | None = None,
    home: Path | None = None,
) -> str | None:
    if not config.persist_session:
        return None

    if (platform_value or sys.platform) == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            path = Path(base) / config.organization_name / config.profile_name / "WebView2"
        else:
            path = persistent_storage_path(
                config.organization_name,
                config.profile_name,
                platform_value,
                home,
            )
    else:
        path = persistent_storage_path(
            config.organization_name,
            config.profile_name,
            platform_value,
            home,
        )
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _show_first_frame(
    window: webview.Window,
    ready: threading.Event,
    config: AppConfig,
) -> None:
    if ready.is_set():
        return

    ready.set()
    window.show()
    if config.start_maximized:
        window.maximize()


def _startup_watchdog(
    window: webview.Window,
    ready: threading.Event,
    config: AppConfig,
) -> None:
    # Avoid leaving the application invisible if a server hangs before DOM ready.
    if ready.wait(timeout=15):
        return

    _show_first_frame(window, ready, config)


def _webview2_controller(native_control: Any) -> Any:
    """Locate the CoreWebView2Controller from the native WebView2 control.

    ``AcceleratorKeyPressed`` lives on the controller, not on ``CoreWebView2``,
    and some SDK versions expose the controller only through a private backing
    field, so this falls back to reflection.
    """
    try:
        controller = getattr(native_control, "CoreWebView2Controller", None)
        if controller is not None:
            return controller
    except Exception:
        pass

    try:
        from System.Reflection import BindingFlags  # type: ignore[import-not-found]

        field = native_control.GetType().GetField(
            "_coreWebView2Controller",
            BindingFlags.NonPublic | BindingFlags.Instance,
        )
        controller = field.GetValue(native_control)
        if controller is not None:
            return controller
    except Exception:
        pass

    return None


def _configure_native_webview(
    window: webview.Window,
    config: AppConfig,
) -> None:
    """Apply WebView2 security settings and navigation policy."""
    native_window = cast(Any, window)
    native_form = cast(Any, native_window.native)
    native_control = cast(Any, native_form.webview)
    core_handlers_attached = False

    if config.app_icon and os.path.exists(config.app_icon):
        try:
            import clr
            add_reference = getattr(clr, "AddReference", None)
            if callable(add_reference):
                add_reference("System.Drawing")
            from System.Drawing import Icon as SystemIcon  # type: ignore[import-not-found,import-untyped]
            native_form.Icon = SystemIcon(os.path.abspath(config.app_icon))
        except Exception:
            pass

    def invoke_on_ui_thread(callback: Any) -> None:
        if native_form.IsDisposed:
            return

        if native_form.InvokeRequired:
            native_form.BeginInvoke(callback)
        else:
            callback()

    def navigation_starting(sender: Any, args: Any) -> None:
        del sender
        destination = str(args.Uri)
        # NavigateToString loads error pages with an about:blank origin; some
        # SDK versions report an empty URI, so treat blank destinations as
        # internal instead of cancelling the application's own error page.
        if not destination or is_navigation_allowed(destination, config):
            return

        args.Cancel = True
        if config.open_external_links:
            webbrowser.open(destination, new=2)

    def apply_core_settings(core: Any) -> None:
        nonlocal core_handlers_attached

        settings = core.Settings
        settings.AreBrowserAcceleratorKeysEnabled = False
        settings.AreDefaultContextMenusEnabled = False
        settings.AreDevToolsEnabled = False
        settings.IsBuiltInErrorPageEnabled = False
        settings.IsStatusBarEnabled = False
        settings.IsSwipeNavigationEnabled = True
        settings.IsZoomControlEnabled = True

        optional_false_settings = (
            "IsPasswordAutosaveEnabled",
            "IsGeneralAutofillEnabled",
            "AreBrowserExtensionsEnabled",
        )
        for setting_name in optional_false_settings:
            if hasattr(settings, setting_name):
                setattr(settings, setting_name, False)

        install_swipe_navigation(core)
        attach_error_page_handler(core)
        core_handlers_attached = True

    swipe_handler_attached = False

    def install_swipe_navigation(core: Any) -> None:
        """Forward touchpad two-finger horizontal swipes to back/forward."""
        nonlocal swipe_handler_attached
        if swipe_handler_attached:
            return

        def on_web_message(sender: Any, args: Any) -> None:
            del sender
            action = _swipe_action_from_message(
                getattr(args, "WebMessageAsJson", None)
            )
            if action == "back":
                invoke_on_ui_thread(lambda: core.GoBack())
            elif action == "forward":
                invoke_on_ui_thread(lambda: core.GoForward())

        try:
            core.WebMessageReceived += on_web_message
            core.AddScriptToExecuteOnDocumentCreatedAsync(_SWIPE_NAVIGATION_SCRIPT)
            core.ExecuteScriptAsync(_SWIPE_NAVIGATION_SCRIPT)
            _NATIVE_HANDLERS.append(on_web_message)
            swipe_handler_attached = True
        except Exception:
            pass

    error_page_handler_attached = False
    error_page_active = False

    def attach_error_page_handler(core: Any) -> None:
        """Replace WebView2's error page with a branded page that hides the URL."""
        nonlocal error_page_handler_attached, error_page_active
        if error_page_handler_attached:
            return

        def navigation_completed(sender: Any, args: Any) -> None:
            nonlocal error_page_active
            del sender
            is_success = bool(getattr(args, "IsSuccess", True))
            if is_success:
                error_page_active = False
                return
            if not _should_show_navigation_error(
                is_success,
                getattr(args, "WebErrorStatus", None),
            ):
                return

            def show_error_page() -> None:
                core.NavigateToString(_navigation_error_html(config))
                try:
                    native_control.Focus()
                except Exception:
                    pass

            error_page_active = True
            invoke_on_ui_thread(show_error_page)

        try:
            core.NavigationCompleted += navigation_completed
            _NATIVE_HANDLERS.append(navigation_completed)
            error_page_handler_attached = True
        except Exception:
            pass

    shortcut_handler_attached = False

    def attach_shortcut_handler() -> None:
        nonlocal shortcut_handler_attached
        if shortcut_handler_attached:
            return
        controller = _webview2_controller(native_control)
        if controller is None:
            return
        if hasattr(controller, "AcceleratorKeyPressed"):
            controller.AcceleratorKeyPressed += webview_shortcut_handler
            shortcut_handler_attached = True

    def initialization_completed(sender: Any, args: Any) -> None:
        if not args.IsSuccess:
            return

        apply_core_settings(sender.CoreWebView2)
        attach_shortcut_handler()

    def webview_shortcut_handler(sender: Any, args: Any) -> None:
        del sender
        key_event_kind = getattr(args, "KeyEventKind", None)
        if key_event_kind is not None:
            try:
                # CoreWebView2KeyEventKind: KeyDown == 0. Ignore key-up so that
                # actions such as reload run once instead of twice.
                if int(key_event_kind) != 0:
                    if hasattr(args, "Handled"):
                        args.Handled = True
                    return
            except (TypeError, ValueError):
                pass
        ctrl, shift, alt = _modifier_state(args)
        action = _shortcut_action(
            getattr(args, "VirtualKey", None)
            or getattr(args, "KeyValue", None)
            or getattr(args, "Key", None),
            ctrl=ctrl,
            shift=shift,
            alt=alt,
        )
        if action is None:
            return

        now = time.monotonic()
        last = _SHORTCUT_LAST_FIRED.get(action, 0.0)
        if now - last < _SHORTCUT_DEBOUNCE_SECONDS:
            if hasattr(args, "Handled"):
                args.Handled = True
            return
        _SHORTCUT_LAST_FIRED[action] = now

        if hasattr(args, "Handled"):
            args.Handled = True

        if action == "close":
            invoke_on_ui_thread(lambda: native_form.Close())
            return

        if action == "fullscreen":
            try:
                invoke_on_ui_thread(lambda: window.toggle_fullscreen())
            except Exception:
                pass
            return

        core_webview = native_control.CoreWebView2
        if core_webview is None:
            return

        if action == "home":
            if not config.web_app_url:
                return
            invoke_on_ui_thread(
                lambda: core_webview.Navigate(config.web_app_url)
            )
            return

        if action == "back":
            try:
                invoke_on_ui_thread(lambda: core_webview.GoBack())
            except Exception:
                pass
            return

        if action == "forward":
            try:
                invoke_on_ui_thread(lambda: core_webview.GoForward())
            except Exception:
                pass
            return

        if action == "reload":
            if error_page_active and config.web_app_url:
                invoke_on_ui_thread(
                    lambda: core_webview.Navigate(config.web_app_url)
                )
            else:
                invoke_on_ui_thread(lambda: core_webview.Reload())
            return

        if action == "hard_reload":
            if error_page_active and config.web_app_url:
                _clear_http_cache(core_webview.Profile)
                invoke_on_ui_thread(
                    lambda: core_webview.Navigate(config.web_app_url)
                )
            else:
                _reload_after_cache_clear(core_webview, invoke_on_ui_thread)
            return

        if action == "clear_browsing_data":
            try:
                invoke_on_ui_thread(lambda: core_webview.Profile.ClearBrowsingDataAsync())
                invoke_on_ui_thread(lambda: core_webview.Reload())
            except Exception:
                pass
            return

        if action == "zoom_in":
            try:
                invoke_on_ui_thread(
                    lambda: setattr(
                        core_webview.Settings,
                        "ZoomFactor",
                        core_webview.Settings.ZoomFactor + 0.1,
                    )
                )
            except Exception:
                pass
            return

        if action == "zoom_out":
            try:
                invoke_on_ui_thread(
                    lambda: setattr(
                        core_webview.Settings,
                        "ZoomFactor",
                        max(0.25, core_webview.Settings.ZoomFactor - 0.1),
                    )
                )
            except Exception:
                pass
            return

        if action == "zoom_reset":
            try:
                invoke_on_ui_thread(lambda: setattr(core_webview.Settings, "ZoomFactor", 1.0))
            except Exception:
                pass
            return

        if action == "find":
            invoke_on_ui_thread(lambda: _open_find_dialog(core_webview))
            return

        if action == "print":
            try:
                invoke_on_ui_thread(lambda: core_webview.PrintAsync())
            except Exception:
                pass
            return

    native_control.NavigationStarting += navigation_starting
    if native_control.CoreWebView2 is not None:
        apply_core_settings(native_control.CoreWebView2)
    else:
        native_control.CoreWebView2InitializationCompleted += initialization_completed

    attach_shortcut_handler()

    # Keep Python/.NET delegates alive for the lifetime of the native window.
    _NATIVE_HANDLERS.extend(
        [
            navigation_starting,
            initialization_completed,
            webview_shortcut_handler,
        ]
    )


def _renderer_initialized(
    renderer: str,
    expected_renderer: str = "edgechromium",
) -> bool | None:
    if renderer != expected_renderer:
        return False
    return None


def _safe_error_html(config: AppConfig, message: str) -> str:
    title = html.escape(config.app_name)
    body = html.escape(message)
    background = html.escape(config.page_background_color)
    foreground = "#f9fafb" if background.lower() != "#ffffff" else "#111827"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
html, body {{
    width: 100%;
    height: 100%;
    margin: 0;
    background: {background};
    color: {foreground};
    font-family: "Segoe UI", system-ui, sans-serif;
}}
main {{
    min-height: 100%;
    display: grid;
    place-items: center;
    padding: 32px;
    box-sizing: border-box;
}}
section {{
    max-width: 560px;
    text-align: center;
}}
h1 {{
    font-size: 24px;
    margin: 0 0 12px;
}}
p {{
    line-height: 1.6;
    margin: 0;
}}
</style>
</head>
<body>
<main>
<section>
<h1>Unable to open {title}</h1>
<p>{body}</p>
</section>
</main>
</body>
</html>"""


# CoreWebView2WebErrorStatus.OperationCanceled. Fires when a navigation is
# cancelled (for example a blocked external link), which is not a real failure.
_OPERATION_CANCELED_WEB_ERROR_STATUS = 14

_NAVIGATION_ERROR_MESSAGE = (
    "The application could not be reached. "
    "Check your connection and try again."
)


def _should_show_navigation_error(is_success: bool, web_error_status: Any) -> bool:
    """Whether a completed navigation should be replaced by the error page.

    Successful loads and user-cancelled navigations (blocked external links)
    are ignored; only genuine failures like timeouts, host resolution errors,
    or TLS problems show the branded error page.
    """
    if is_success:
        return False
    try:
        if web_error_status is not None and int(web_error_status) == (
            _OPERATION_CANCELED_WEB_ERROR_STATUS
        ):
            return False
    except (TypeError, ValueError):
        pass
    return True


def _navigation_error_html(config: AppConfig) -> str:
    """Branded error page that never exposes the failed URL."""
    return _safe_error_html(config, _NAVIGATION_ERROR_MESSAGE)


def run_browser(config: AppConfig) -> int:
    webview.settings["ALLOW_DOWNLOADS"] = config.allow_downloads
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["IGNORE_SSL_ERRORS"] = False
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    webview.settings["REMOTE_DEBUGGING_PORT"] = None
    webview.settings["SHOW_DEFAULT_MENUS"] = False

    ready = threading.Event()

    window = webview.create_window(
        title=config.app_name,
        url=config.web_app_url,
        width=config.window_width,
        height=config.window_height,
        min_size=(800, 600),
        resizable=True,
        hidden=True,
        maximized=config.start_maximized,
        background_color=config.page_background_color,
        text_select=True,
        zoomable=False,
        draggable=False,
        confirm_close=False,
    )

    window_any = cast(Any, window)
    window_events = window_any.events

    backend = browser_backend()
    expected_renderer = renderer_name()
    window_events.initialized += (
        lambda renderer: _renderer_initialized(renderer, expected_renderer)
    )
    if backend == "edgechromium":
        window_events.before_show += (
            lambda window: _configure_native_webview(window, config)
        )
    else:
        from app.macos import configure_macos_webview

        window_events.before_show += (
            lambda window: configure_macos_webview(window, config)
        )
    window_events.loaded += (
        lambda window: _show_first_frame(window, ready, config)
    )

    storage_path = _storage_path(config)

    try:
        webview.start(
            func=_startup_watchdog,
            args=(window, ready, config),
            gui=backend,
            debug=False,
            private_mode=not config.persist_session,
            storage_path=storage_path,
        )
    except Exception:
        try:
            cast(Any, window).load_html(
                _safe_error_html(
                    config,
                    "The native web renderer failed to initialize.",
                )
            )
            cast(Any, window).show()
        except Exception:
            pass
        return 4

    return 0
