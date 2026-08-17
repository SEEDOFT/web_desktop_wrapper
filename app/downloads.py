from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from app.config import AppConfig
from app.logger import get_logger

logger = get_logger(__name__)


def show_download_notification(
    title: str,
    message: str,
    tray_icon: Any = None,
) -> None:
    """Display a native notification toast or system tray balloon."""
    if tray_icon is not None:
        try:
            tray_icon.ShowBalloonTip(3000, title, message, 1)  # 1 = ToolTipIcon.Info
            return
        except Exception as e:
            logger.debug("Failed to show tray balloon tip: %s", e)

    # Windows fallback via ctypes or console log
    logger.info("[Notification] %s: %s", title, message)


def setup_download_handler(
    core: Any,
    config: AppConfig,
    invoke_on_ui_thread: Any,
    tray_icon: Any = None,
) -> None:
    """Attach download management, custom download directory, and completion toasts to WebView2."""
    if not hasattr(core, "DownloadStarting"):
        return

    default_dir: Path | None = None
    if config.default_downloads_path:
        try:
            default_dir = Path(config.default_downloads_path).expanduser().resolve()
            default_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Failed to initialize custom downloads directory: %s", e)
            default_dir = None

    def on_download_starting(sender: Any, args: Any) -> None:
        del sender
        if not config.allow_downloads:
            args.Cancel = True
            logger.warning("Blocked file download attempt because ALLOW_DOWNLOADS is false.")
            return

        operation = getattr(args, "DownloadOperation", None)
        file_name = "file"
        try:
            suggested_path = getattr(args, "ResultFilePath", "")
            if suggested_path:
                file_name = Path(str(suggested_path)).name
                if default_dir is not None:
                    target_file = default_dir / file_name
                    args.ResultFilePath = str(target_file)
        except Exception as e:
            logger.debug("Failed to set custom download path: %s", e)

        if operation is not None and hasattr(operation, "StateChanged"):
            def on_state_changed(op_sender: Any, op_args: Any) -> None:
                del op_args
                try:
                    # 1 = Completed, 2 = Interrupted
                    state = getattr(op_sender, "State", None)
                    state_int = int(state) if state is not None else -1
                    if state_int == 1:
                        logger.info("Download completed successfully: %s", file_name)
                        if config.show_download_notifications:
                            invoke_on_ui_thread(
                                lambda: show_download_notification(
                                    config.app_name,
                                    f"Download complete: {file_name}",
                                    tray_icon,
                                )
                            )
                    elif state_int == 2:
                        logger.warning("Download interrupted or failed: %s", file_name)
                except Exception as e:
                    logger.debug("Error in download state changed handler: %s", e)

            operation.StateChanged += on_state_changed

    try:
        core.DownloadStarting += on_download_starting
        logger.debug("Download management handler attached.")
    except Exception as e:
        logger.warning("Failed to attach download starting handler: %s", e)
