from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.config import AppConfig
from app.logger import get_logger

logger = get_logger(__name__)

_GLOBAL_TRAY_ICON: Any = None
_IS_QUITTING = False


def cleanup_system_tray() -> None:
    """Clean up and dispose the system tray icon to prevent orphaned icons."""
    global _GLOBAL_TRAY_ICON
    if _GLOBAL_TRAY_ICON is not None:
        try:
            _GLOBAL_TRAY_ICON.Visible = False
            _GLOBAL_TRAY_ICON.Dispose()
        except Exception as e:
            logger.debug("Failed to dispose system tray icon: %s", e)
        _GLOBAL_TRAY_ICON = None


def setup_system_tray(
    window: Any,
    native_form: Any,
    config: AppConfig,
    invoke_on_ui_thread: Any,
    native_control: Any = None,
) -> Any:
    """Initialize system tray icon with context menu and minimize-to-tray handling."""
    global _GLOBAL_TRAY_ICON, _IS_QUITTING
    _IS_QUITTING = False

    if not config.enable_tray or sys.platform != "win32":
        return None

    try:
        from System.Drawing import Icon  # type: ignore[import-not-found]
        from System.Windows.Forms import (  # type: ignore[import-not-found]
            ContextMenuStrip,
            FormWindowState,
            NotifyIcon,
            ToolStripSeparator,
        )

        tray = NotifyIcon()
        _GLOBAL_TRAY_ICON = tray

        # Set tray icon from form or icon file
        if native_form.Icon is not None:
            tray.Icon = native_form.Icon
        elif config.app_icon and Path(config.app_icon).is_file():
            try:
                tray.Icon = Icon(str(Path(config.app_icon).resolve()))
            except Exception as e:
                logger.debug("Failed to load tray icon from file: %s", e)

        # Windows limits tooltip to 63 chars
        tray.Text = config.app_name[:63]

        def restore_window() -> None:
            def _restore() -> None:
                native_form.Show()
                if native_form.WindowState == FormWindowState.Minimized:
                    native_form.WindowState = FormWindowState.Normal
                native_form.Activate()
                native_form.BringToFront()

            invoke_on_ui_thread(_restore)

        def reload_app() -> None:
            def _reload() -> None:
                if native_control and getattr(native_control, "CoreWebView2", None):
                    native_control.CoreWebView2.Reload()
                elif config.web_app_url:
                    window.load_url(config.web_app_url)

            invoke_on_ui_thread(_reload)

        def quit_app() -> None:
            global _IS_QUITTING
            _IS_QUITTING = True

            def _quit() -> None:
                cleanup_system_tray()
                native_form.Close()

            invoke_on_ui_thread(_quit)

        # Context Menu
        menu = ContextMenuStrip()

        item_open = menu.Items.Add(f"Open {config.app_name}")
        item_open.Click += lambda sender, args: restore_window()

        item_reload = menu.Items.Add("Reload")
        item_reload.Click += lambda sender, args: reload_app()

        menu.Items.Add(ToolStripSeparator())

        item_quit = menu.Items.Add("Exit")
        item_quit.Click += lambda sender, args: quit_app()

        tray.ContextMenuStrip = menu
        tray.DoubleClick += lambda sender, args: restore_window()
        tray.Visible = True

        # Minimize to tray handling
        if config.minimize_to_tray:
            shown_balloon = {"shown": False}

            def on_form_closing(sender: Any, e: Any) -> None:
                if not _IS_QUITTING:
                    e.Cancel = True
                    native_form.Hide()
                    if not shown_balloon["shown"]:
                        try:
                            tray.ShowBalloonTip(
                                2000,
                                config.app_name,
                                "Application minimized to system tray.",
                                1,  # Info icon
                            )
                            shown_balloon["shown"] = True
                        except Exception:
                            pass

            native_form.FormClosing += on_form_closing

        logger.info("System tray initialized successfully.")
        return tray
    except Exception as e:
        logger.warning("Failed to initialize system tray: %s", e)
        return None
