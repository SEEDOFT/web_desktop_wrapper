from __future__ import annotations

import ctypes
import os
import sys

from app.browser import run_browser
from app.config import AppConfig, ConfigError
from app.runtime import find_webview2_runtime
from app.platform import runtime_check_required

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
        config = AppConfig.load()
    except ConfigError as exc:
        _message_box("Configuration error", str(exc))
        return 2

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
