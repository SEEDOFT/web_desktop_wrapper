from __future__ import annotations

import ctypes
import os
import sys

from app.browser import run_browser
from app.config import AppConfig, ConfigError
from app.logger import get_logger
from app.platforms import runtime_check_required
from app.runtime import find_webview2_runtime
from app.single_instance import acquire_single_instance

logger = get_logger(__name__)

_IS_WINDOWS = os.name == "nt"
_IS_MACOS = sys.platform == "darwin"


def _message_box(title: str, message: str) -> None:
    if _IS_WINDOWS:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    elif _IS_MACOS:
        try:
            import AppKit  # type: ignore[import-not-found]

            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(message)
            alert.setAlertStyle_(AppKit.NSAlertStyleCritical)
            alert.addButtonWithTitle_("OK")
            alert.runModal()
        except Exception:
            print(f"{title}: {message}")
    else:
        print(f"{title}: {message}")


def run() -> int:
    if not (_IS_WINDOWS or _IS_MACOS):
        _message_box(
            "Unsupported operating system",
            "This application requires Windows or macOS.",
        )
        return 3

    try:
        try:
            config = AppConfig.load()
        except ConfigError as exc:
            _message_box("Configuration error", str(exc))
            return 2

        # Single-instance enforcement
        lock = None
        if config.single_instance:
            lock = acquire_single_instance(config.profile_name, config.app_name)
            if lock is None:
                logger.info("Application already running; focusing active instance and exiting.")
                return 0

        # Auto-start synchronization
        try:
            from app.autostart import sync_autostart
            sync_autostart(config.app_name, config.organization_name, config.run_on_startup)
        except Exception as e:
            logger.debug("Failed to sync autostart: %s", e)

        try:
            if runtime_check_required():
                runtime = find_webview2_runtime()
                if not runtime.available:
                    _message_box(
                        config.app_name,
                        "Microsoft Edge WebView2 Runtime is required. "
                        "Install the Evergreen WebView2 Runtime, then reopen the application.",
                    )
                    return 3

            return run_browser(config)
        finally:
            if lock:
                lock.release()
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.critical("Fatal application error:\n%s", tb)
        _message_box("Application Error", f"An unexpected error occurred:\n\n{exc}\n\n{tb}")
        return 1
