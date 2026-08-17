from __future__ import annotations

import html
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Literal, cast

try:
    from System import EventArgs  # type: ignore
except Exception:  # pragma: no cover - Windows-only import guard
    EventArgs = Any  # type: ignore

import webview

from app.config import AppConfig
from app.constants import (
    KEYBOARD_KEY_CODES,
    NAVIGATION_ERROR_MESSAGE,
    OPERATION_CANCELED_WEB_ERROR_STATUS,
    SHORTCUT_DEBOUNCE_SECONDS,
    SWIPE_COOLDOWN_MS,
    SWIPE_THRESHOLD_PIXELS,
)
from app.logger import get_logger
from app.navigation import is_navigation_allowed
from app.platforms import browser_backend, persistent_storage_path, renderer_name

logger = get_logger(__name__)

# Type aliases for improved clarity and type checking
NavigationAction = Literal[
    "back",
    "forward",
    "reload",
    "hard_reload",
    "home",
    "close",
    "fullscreen",
    "zoom_in",
    "zoom_out",
    "zoom_reset",
    "find",
    "print",
    "clear_browsing_data",
]
"""Valid keyboard shortcut actions that can be triggered by the user."""

# Thread-safe storage for native event handlers to prevent garbage collection
_NATIVE_HANDLERS: list[Any] = []
_NATIVE_HANDLERS_LOCK = threading.Lock()

# Thread-safe storage for last fired shortcuts to implement debouncing
_SHORTCUT_LAST_FIRED: dict[str, float] = {}
_SHORTCUT_LAST_FIRED_LOCK = threading.Lock()


def _register_native_handler(handler: Any) -> None:
    """Register a native event handler to keep it alive during the application.
    
    This prevents Python garbage collection of .NET event handler delegates
    that need to survive until the application exits.
    
    Args:
        handler: A native event handler callback or delegate.
    """
    with _NATIVE_HANDLERS_LOCK:
        _NATIVE_HANDLERS.append(handler)


def _cleanup_native_handlers() -> None:
    """Clean up all registered native event handlers.
    
    This should be called during application shutdown to explicitly release
    references to event handlers and allow for proper .NET cleanup.
    """
    with _NATIVE_HANDLERS_LOCK:
        _NATIVE_HANDLERS.clear()
    logger.debug("Native event handlers cleaned up")

from app.scripts_loader import get_script


def _get_swipe_navigation_script() -> str:
    return get_script(
        "swipe_navigation.js",
        THRESHOLD=SWIPE_THRESHOLD_PIXELS,
        COOLDOWN_MS=SWIPE_COOLDOWN_MS,
    )


def _swipe_action_from_message(message_json: str | None) -> Literal["back", "forward"] | None:
    """Map a ``horizontalSwipe`` host message to a navigation action.
    
    Args:
        message_json: JSON string from WebView postMessage containing swipe info
    
    Returns:
        "back" or "forward" for valid swipes, None otherwise.
    """
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
    except Exception as e:
        logger.debug("OpenFindDialog not available: %s", e)

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
        options: Any = create_options()
        if options is not None:
            setattr(options, "FindTerm", "")
            setattr(options, "SuppressDefaultFindDialog", False)
            find.StartAsync(options)
    except Exception as e:
        logger.debug("Failed to open find dialog with StartAsync: %s", e)


def _shortcut_action(
    key: str | int | None,
    ctrl: bool = False,
    shift: bool = False,
    alt: bool = False,
) -> NavigationAction | None:
    """Map a keyboard key combination to a navigation action.
    
    Args:
        key: Virtual key code (int) or key name (str)
        ctrl: Whether Ctrl/Cmd modifier is pressed
        shift: Whether Shift modifier is pressed
        alt: Whether Alt modifier is pressed
    
    Returns:
        The corresponding navigation action, or None if not recognized.
    """
    if key is None:
        return None

    if isinstance(key, int):
        normalized_key = KEYBOARD_KEY_CODES.get(key)
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
    """Extract keyboard modifier state from event arguments.
    
    Args:
        args: Event arguments containing modifier key information
    
    Returns:
        Tuple of (ctrl_pressed, shift_pressed, alt_pressed)
    """
    ctrl = bool(getattr(args, "Control", False) or getattr(args, "Ctrl", False))
    shift = bool(getattr(args, "Shift", False))
    alt = bool(getattr(args, "Alt", False))

    try:
        from System.Windows.Forms import Control, Keys  # type: ignore
    except ImportError:
        logger.debug("System.Windows.Forms not available for modifier state detection")
        return ctrl, shift, alt

    try:
        modifier_keys = Control.ModifierKeys
        ctrl = ctrl or bool(modifier_keys & Keys.Control)
        shift = shift or bool(modifier_keys & Keys.Shift)
        alt = alt or bool(modifier_keys & Keys.Alt)
    except Exception as e:
        logger.debug("Failed to query System.Windows.Forms ModifierKeys: %s", e)

    return ctrl, shift, alt


def _clear_http_cache(profile: Any) -> Any | None:
    """Clear only the HTTP cache so a reload ignores stale redirects to the
    login page without dropping session cookies or DOM storage.
    
    Args:
        profile: WebView2 CoreWebView2Profile object
    
    Returns:
        Async task for cache clearing, or None if operation not available.
    """
    try:
        import System  # type: ignore

        kinds_type = profile.GetType().Assembly.GetType(
            "Microsoft.Web.WebView2.Core.CoreWebView2BrowsingDataKinds"
        )
        if kinds_type is None:
            logger.debug("CoreWebView2BrowsingDataKinds type not found")
            return None
        cache_kinds = None
        for candidate in ("DiskCache", "CacheStorage"):
            try:
                cache_kinds = System.Enum.Parse(kinds_type, candidate)
                break
            except Exception as e:
                logger.debug("Could not parse browsing data kind '%s': %s", candidate, e)
                continue
        if cache_kinds is None:
            logger.debug("No supported browsing data kinds found")
            return None
        return profile.ClearBrowsingDataAsync(cache_kinds)
    except Exception as e:
        logger.warning("Failed to clear HTTP cache: %s", e)
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
        _register_native_handler(callback)
        task.GetAwaiter().OnCompleted(callback)
    except Exception as e:
        # Older WebView2/pythonnet combinations may not expose an awaiter.
        # A normal reload remains safe and preserves cookies/site storage.
        logger.debug("Awaiter pattern not available, using direct reload: %s", e)
        invoke_on_ui_thread(lambda: core_webview.Reload())


def _storage_path(
    config: AppConfig,
    platform_value: str | None = None,
    home: Path | None = None,
) -> str | None:
    """Calculate the persistent storage path for WebView2 session data.
    
    Args:
        config: Application configuration
        platform_value: Override platform detection (mainly for testing)
        home: Override home directory path (mainly for testing)
    
    Returns:
        Path to storage directory, or None if persistence is disabled.
    """
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
    """Reveal the main window once the first page load completes."""
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
    """Avoid leaving the application invisible if a server hangs before DOM ready."""
    if ready.wait(timeout=15):
        return

    _show_first_frame(window, ready, config)


def _splash_transition(
    window: webview.Window,
    config: AppConfig,
) -> None:
    """Run in a background thread when splash is enabled.

    The main window is already visible with the splash HTML as its initial
    content.  This function:
      1. Holds the splash for ``config.splash_duration`` seconds so the
         breathing animation plays at its intended pace.
      2. Triggers the CSS dissolve animation (opacity → 0, scale → 0.96,
         blur → 18 px) over 1.2 s.
      3. Navigates the *same* window to the real web application URL.
    Because everything happens inside a single window there is no secondary
    window, no background flash, and no coordination gap — identical to how
    Once Human transitions from its loading screen to gameplay.
    """
    time.sleep(config.splash_duration)

    # Trigger the CSS dissolve class
    try:
        window.evaluate_js("window.fadeOut && window.fadeOut();")
    except Exception as e:
        logger.debug("Splash fadeOut JS failed: %s", e)

    # Let the CSS dissolve animation play (1.4 s transition duration)
    time.sleep(1.4)

    # Navigate the same window to the actual web application
    window.load_url(config.web_app_url)


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
    except Exception as e:
        logger.debug("CoreWebView2Controller property not available: %s", e)

    try:
        from System.Reflection import BindingFlags  # type: ignore[import-not-found]

        field = native_control.GetType().GetField(
            "_coreWebView2Controller",
            BindingFlags.NonPublic | BindingFlags.Instance,
        )
        controller = field.GetValue(native_control)
        if controller is not None:
            return controller
    except Exception as e:
        logger.debug("Could not access CoreWebView2Controller via reflection: %s", e)

    return None


def _is_dark_color(hex_color: str) -> bool:
    """Determine whether a hex color string represents a dark color."""
    cleaned = hex_color.lstrip("#")
    if len(cleaned) == 6:
        try:
            r = int(cleaned[0:2], 16)
            g = int(cleaned[2:4], 16)
            b = int(cleaned[4:6], 16)
            return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128
        except ValueError:
            pass
    return False


def _apply_window_icon(native_form: Any, app_icon: str) -> None:
    """Apply application icon to Windows Form."""
    if not app_icon or not os.path.exists(app_icon):
        return
    try:
        import clr
        add_reference = getattr(clr, "AddReference", None)
        if callable(add_reference):
            add_reference("System.Drawing")
        from System.Drawing import Icon as SystemIcon  # type: ignore[import-not-found,import-untyped]
        native_form.Icon = SystemIcon(os.path.abspath(app_icon))
    except Exception as e:
        logger.warning("Failed to set application icon: %s", e)


def _apply_dark_mode_titlebar(native_form: Any, background_color: str) -> None:
    """Set dark mode titlebar on Windows 10/11 if background color is dark."""
    if sys.platform != "win32" or not _is_dark_color(background_color):
        return
    try:
        handle = getattr(native_form, "Handle", None)
        if handle is None:
            return
        hwnd = int(getattr(handle, "ToInt64", lambda: int(handle))())
        if not hwnd:
            return

        import ctypes
        from ctypes import wintypes

        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(1)
        for attr in (20, 19):
            hr = dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                ctypes.c_uint(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if hr == 0:
                break
    except Exception as e:
        logger.debug("Failed to set dark mode titlebar: %s", e)


def _attach_swipe_navigation(core: Any, invoke_on_ui_thread: Any) -> None:
    """Forward touchpad two-finger horizontal swipes to back/forward."""
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
        swipe_script = _get_swipe_navigation_script()
        core.WebMessageReceived += on_web_message
        if swipe_script:
            core.AddScriptToExecuteOnDocumentCreatedAsync(swipe_script)
            core.ExecuteScriptAsync(swipe_script)
        _register_native_handler(on_web_message)
    except Exception as e:
        logger.warning("Failed to install swipe navigation: %s", e)


def _attach_error_page_handler(
    core: Any,
    native_control: Any,
    config: AppConfig,
    invoke_on_ui_thread: Any,
    error_state: dict[str, bool],
) -> None:
    """Replace WebView2's error page with a branded page that hides the URL."""
    def navigation_completed(sender: Any, args: Any) -> None:
        del sender
        is_success = bool(getattr(args, "IsSuccess", True))
        source = str(getattr(core, "Source", "") or "").lower()

        if is_success:
            # Only reset error state if we successfully loaded a real remote/local URL,
            # not the NavigateToString error page or about:blank.
            if source and source != "about:blank" and not source.startswith("data:"):
                error_state["active"] = False
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
            except Exception as e:
                logger.debug("Failed to focus native control: %s", e)

        error_state["active"] = True
        invoke_on_ui_thread(show_error_page)

    try:
        core.NavigationCompleted += navigation_completed
        _register_native_handler(navigation_completed)
    except Exception as e:
        logger.warning("Failed to attach error page handler: %s", e)


def _create_shortcut_handler(
    window: webview.Window,
    native_form: Any,
    native_control: Any,
    config: AppConfig,
    invoke_on_ui_thread: Any,
    error_state: dict[str, bool],
) -> Any:
    """Create the AcceleratorKeyPressed shortcut handler for WebView2."""
    def webview_shortcut_handler(sender: Any, args: Any) -> None:
        del sender
        key_event_kind = getattr(args, "KeyEventKind", None)
        if key_event_kind is not None:
            try:
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
        with _SHORTCUT_LAST_FIRED_LOCK:
            last = _SHORTCUT_LAST_FIRED.get(action, 0.0)
            if now - last < SHORTCUT_DEBOUNCE_SECONDS:
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
            except Exception as e:
                logger.debug("Failed to toggle fullscreen: %s", e)
            return

        core_webview = native_control.CoreWebView2
        if core_webview is None:
            return

        # Determine if we are currently displaying the error page or a blank state
        current_source = str(getattr(core_webview, "Source", "") or "").lower()
        is_error_or_blank = (
            error_state.get("active", False)
            or not current_source
            or current_source in {"about:blank", ""}
            or current_source.startswith("data:")
        )

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
            except Exception as e:
                logger.debug("Failed to navigate back: %s", e)
            return

        if action == "forward":
            try:
                invoke_on_ui_thread(lambda: core_webview.GoForward())
            except Exception as e:
                logger.debug("Failed to navigate forward: %s", e)
            return

        if action == "reload":
            if is_error_or_blank and config.web_app_url:
                invoke_on_ui_thread(
                    lambda: core_webview.Navigate(config.web_app_url)
                )
            else:
                invoke_on_ui_thread(lambda: core_webview.Reload())
            return

        if action == "hard_reload":
            if is_error_or_blank and config.web_app_url:
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
            except Exception as e:
                logger.debug("Failed to clear browsing data: %s", e)
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
            except Exception as e:
                logger.debug("Failed to zoom in: %s", e)
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
            except Exception as e:
                logger.debug("Failed to zoom out: %s", e)
            return

        if action == "zoom_reset":
            try:
                invoke_on_ui_thread(lambda: setattr(core_webview.Settings, "ZoomFactor", 1.0))
            except Exception as e:
                logger.debug("Failed to reset zoom: %s", e)
            return

        if action == "find":
            invoke_on_ui_thread(lambda: _open_find_dialog(core_webview))
            return

        if action == "print":
            try:
                invoke_on_ui_thread(lambda: core_webview.PrintAsync())
            except Exception as e:
                logger.debug("Failed to print: %s", e)
            return

    return webview_shortcut_handler


def _configure_native_webview(
    window: webview.Window,
    config: AppConfig,
) -> None:
    """Apply WebView2 security settings, dark titlebars, and event handlers."""
    native_window = cast(Any, window)
    native_form = cast(Any, native_window.native)
    native_control = cast(Any, native_form.webview)
    error_state = {"active": False}

    _apply_window_icon(native_form, config.app_icon)
    _apply_dark_mode_titlebar(native_form, config.page_background_color)

    def invoke_on_ui_thread(callback: Any) -> None:
        if native_form.IsDisposed:
            return

        if native_form.InvokeRequired:
            native_form.BeginInvoke(callback)
        else:
            callback()

    def navigation_starting(sender: Any, args: Any) -> None:
        del sender
        destination = str(getattr(args, "Uri", "") or "")

        # If a reload is triggered while showing an error page, redirect to the main web app
        if error_state.get("active") and (
            not destination or destination == "about:blank" or destination.startswith("data:")
        ):
            if config.web_app_url and native_control.CoreWebView2 is not None:
                args.Cancel = True
                invoke_on_ui_thread(
                    lambda: native_control.CoreWebView2.Navigate(config.web_app_url)
                )
                return

        if not destination or is_navigation_allowed(destination, config):
            return

        args.Cancel = True
        if config.open_external_links:
            webbrowser.open(destination, new=2)

    # System Tray Integration
    tray_icon = None
    if config.enable_tray:
        try:
            from app.tray import setup_system_tray
            tray_icon = setup_system_tray(
                window, native_form, config, invoke_on_ui_thread, native_control
            )
        except Exception as e:
            logger.debug("Failed to initialize tray icon: %s", e)

    def apply_core_settings(core: Any) -> None:
        settings = core.Settings
        settings.AreBrowserAcceleratorKeysEnabled = False
        settings.AreDefaultContextMenusEnabled = False
        settings.AreDevToolsEnabled = False
        settings.IsBuiltInErrorPageEnabled = False
        settings.IsStatusBarEnabled = False
        settings.IsSwipeNavigationEnabled = True
        settings.IsZoomControlEnabled = True

        for setting_name in (
            "IsPasswordAutosaveEnabled",
            "IsGeneralAutofillEnabled",
            "AreBrowserExtensionsEnabled",
        ):
            if hasattr(settings, setting_name):
                setattr(settings, setting_name, False)

        # Custom User-Agent configuration
        if config.user_agent and hasattr(settings, "UserAgent"):
            try:
                setattr(settings, "UserAgent", config.user_agent)
            except Exception as e:
                logger.debug("Failed to set custom User-Agent: %s", e)

        # Attach X-Wrapper-Version header to all HTTP requests in WebView2
        if config.wrapper_version and hasattr(core, "AddWebResourceRequestedFilter"):
            try:
                # 0 corresponds to CoreWebView2WebResourceContext.All
                core.AddWebResourceRequestedFilter("*", 0)

                def _on_web_resource_requested(sender: Any, args: Any) -> None:
                    del sender
                    try:
                        args.Request.Headers.SetHeader("X-Wrapper-Version", config.wrapper_version)
                    except Exception:
                        pass

                core.WebResourceRequested += _on_web_resource_requested
            except Exception as e:
                logger.debug("Failed to attach WebResourceRequested filter: %s", e)

        # Inject X-Wrapper-Version into client-side fetch and XMLHttpRequest
        if config.wrapper_version and hasattr(core, "AddScriptToExecuteOnDocumentCreatedAsync"):
            try:
                header_script = get_script(
                    "wrapper_version_header.js",
                    WRAPPER_VERSION=config.wrapper_version,
                )
                if header_script:
                    core.AddScriptToExecuteOnDocumentCreatedAsync(header_script)
            except Exception as e:
                logger.debug("Failed to attach X-Wrapper-Version user script: %s", e)

        # Drag-and-drop hardening (prevent accidental file drops from navigating away)
        if not config.allow_file_drop and hasattr(core, "AddScriptToExecuteOnDocumentCreatedAsync"):
            try:
                drop_script = get_script("prevent_file_drop.js")
                if drop_script:
                    core.AddScriptToExecuteOnDocumentCreatedAsync(drop_script)
            except Exception as e:
                logger.debug("Failed to attach drag-drop hardening script: %s", e)

        _attach_swipe_navigation(core, invoke_on_ui_thread)
        _attach_error_page_handler(core, native_control, config, invoke_on_ui_thread, error_state)

        # Download Management & Completion Notifications
        try:
            from app.downloads import setup_download_handler
            setup_download_handler(core, config, invoke_on_ui_thread, tray_icon)
        except Exception as e:
            logger.debug("Failed to attach download handler: %s", e)

    shortcut_handler = _create_shortcut_handler(
        window, native_form, native_control, config, invoke_on_ui_thread, error_state
    )

    def attach_shortcut_handler() -> None:
        controller = _webview2_controller(native_control)
        if controller is not None and hasattr(controller, "AcceleratorKeyPressed"):
            controller.AcceleratorKeyPressed += shortcut_handler

    def initialization_completed(sender: Any, args: Any) -> None:
        if not args.IsSuccess:
            return
        apply_core_settings(sender.CoreWebView2)
        attach_shortcut_handler()

    native_control.NavigationStarting += navigation_starting
    if native_control.CoreWebView2 is not None:
        apply_core_settings(native_control.CoreWebView2)
    else:
        native_control.CoreWebView2InitializationCompleted += initialization_completed

    attach_shortcut_handler()

    # Keep Python/.NET delegates alive for the lifetime of the native window.
    _register_native_handler(navigation_starting)
    _register_native_handler(initialization_completed)
    _register_native_handler(shortcut_handler)


def _renderer_initialized(
    renderer: str,
    expected_renderer: str = "edgechromium",
) -> bool | None:
    if renderer != expected_renderer:
        return False
    return None


def _safe_error_html(config: AppConfig, body: str) -> str:
    title = html.escape(config.app_name)
    background = config.page_background_color
    foreground = "#ffffff" if _is_dark_color(background) else "#111827"
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
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    user-select: none;
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
    font-weight: 700;
}}
p {{
    line-height: 1.6;
    margin: 0 0 20px;
    opacity: 0.85;
}}
.retry-btn {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 24px;
    background: #0284c7;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(2, 132, 199, 0.35);
    transition: background 0.2s, transform 0.1s, opacity 0.2s;
}}
.retry-btn:hover {{
    background: #0369a1;
}}
.retry-btn:active {{
    transform: scale(0.97);
}}
.retry-btn:disabled {{
    opacity: 0.6;
    cursor: not-allowed;
}}
.shortcut-hint {{
    margin-top: 16px;
    font-size: 12px;
    opacity: 0.6;
}}
kbd {{
    display: inline-block;
    padding: 2px 6px;
    font-family: monospace;
    font-size: 11px;
    background: rgba(128, 128, 128, 0.15);
    border: 1px solid rgba(128, 128, 128, 0.3);
    border-radius: 4px;
}}
</style>
<script>
function retryConnection() {{
    var btn = document.getElementById('retry-btn');
    if (btn) {{
        btn.textContent = 'Reconnecting...';
        btn.disabled = true;
    }}
    window.location.reload();
}}
window.addEventListener('keydown', function(e) {{
    // F5 (116) or Ctrl+R / Cmd+R (82)
    if (e.keyCode === 116 || ((e.ctrlKey || e.metaKey) && e.keyCode === 82)) {{
        e.preventDefault();
        retryConnection();
    }}
}});
window.addEventListener('online', function() {{
    retryConnection();
}});
</script>
</head>
<body>
<main>
<section>
<h1>Unable to open {title}</h1>
<p>{html.escape(body)}</p>
<button id="retry-btn" class="retry-btn" onclick="retryConnection()">Retry Connection</button>
<div class="shortcut-hint">Press <kbd>F5</kbd> or <kbd>Ctrl+R</kbd> to retry</div>
</section>
</main>
</body>
</html>"""


# CoreWebView2WebErrorStatus.OperationCanceled. Fires when a navigation is
# cancelled (for example a blocked external link), which is not a real failure.


def _should_show_navigation_error(is_success: bool, web_error_status: Any) -> bool:
    """Whether a completed navigation should be replaced by the error page.

    Successful loads and user-cancelled navigations (blocked external links)
    are ignored; only genuine failures like timeouts, host resolution errors,
    or TLS problems show the branded error page.
    
    Args:
        is_success: Whether the navigation completed successfully
        web_error_status: WebView2 error status code if navigation failed
    
    Returns:
        True if a branded error page should be shown, False otherwise.
    """
    if is_success:
        return False
    try:
        if web_error_status is not None and int(web_error_status) == (
            OPERATION_CANCELED_WEB_ERROR_STATUS
        ):
            return False
    except (TypeError, ValueError):
        pass
    return True


def _navigation_error_html(config: AppConfig) -> str:
    """Branded error page that never exposes the failed URL."""
    return _safe_error_html(config, NAVIGATION_ERROR_MESSAGE)


def _cleanup_all_handlers() -> None:
    """Clean up native Windows and macOS handlers, monitors, and system tray icons."""
    _cleanup_native_handlers()
    try:
        from app.tray import cleanup_system_tray
        cleanup_system_tray()
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            from app.macos import cleanup_macos_handlers
            cleanup_macos_handlers()
        except Exception:
            pass


def run_browser(config: AppConfig) -> int:
    """Initialize and run the WebView2 / WKWebView browser application."""
    webview.settings["ALLOW_DOWNLOADS"] = config.allow_downloads
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["IGNORE_SSL_ERRORS"] = False
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    webview.settings["REMOTE_DEBUGGING_PORT"] = None
    webview.settings["SHOW_DEFAULT_MENUS"] = False

    ready = threading.Event()

    # ── decide between splash mode and direct mode ──────────────────────
    use_splash = config.show_splash
    splash_html: str | None = None
    splash_background = "#030712"
    if use_splash:
        try:
            from app.splash import SPLASH_BACKGROUND, generate_splash_html
            splash_background = SPLASH_BACKGROUND
            splash_html = generate_splash_html(config)
        except Exception as e:
            logger.warning("Failed to generate splash HTML: %s", e)
            use_splash = False

    if use_splash and splash_html:
        # Splash mode: window opens immediately with splash HTML content.
        # The dark background_color matches the splash CSS so there is zero
        # visual discontinuity between the native window chrome and the
        # rendered HTML content.
        window = webview.create_window(
            title=config.app_name,
            html=splash_html,
            width=config.window_width,
            height=config.window_height,
            min_size=(800, 600),
            resizable=True,
            hidden=False,
            maximized=config.start_maximized,
            background_color=splash_background,
            text_select=True,
            zoomable=False,
            draggable=False,
            confirm_close=False,
        )
        # Window is already visible; mark ready so _show_first_frame is a
        # no-op if it ever gets called by the loaded event after navigation.
        ready.set()
    else:
        # Direct mode: window starts hidden, shown on first web page load.
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

    # ── event wiring (shared by both modes) ─────────────────────────────
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

    if not use_splash:
        # Direct mode: reveal the window after the first successful load.
        window_events.loaded += (
            lambda window: _show_first_frame(window, ready, config)
        )

    # ── determine startup function ──────────────────────────────────────
    if use_splash:
        startup_func = _splash_transition
        startup_args = (window, config)
    else:
        startup_func = _startup_watchdog
        startup_args = (window, ready, config)

    storage_path = _storage_path(config)

    try:
        webview.start(
            func=startup_func,
            args=startup_args,
            gui=backend,
            debug=False,
            private_mode=not config.persist_session,
            storage_path=storage_path,
        )
    except Exception as e:
        logger.error("WebView2 initialization failed: %s", e)
        try:
            cast(Any, window).load_html(
                _safe_error_html(
                    config,
                    "The native web renderer failed to initialize.",
                )
            )
            cast(Any, window).show()
        except Exception as show_error:
            logger.error("Failed to show error page: %s", show_error)
        finally:
            _cleanup_all_handlers()
        return 4

    # Clean up event handlers on normal exit
    _cleanup_all_handlers()
    return 0

