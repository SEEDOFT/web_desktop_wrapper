from __future__ import annotations

import sys
from pathlib import Path

from app.logger import get_logger

logger = get_logger(__name__)

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart_windows(app_name: str, app_path: str, enable: bool) -> bool:
    """Register or unregister application in Windows CurrentVersion\\Run registry."""
    if sys.platform != "win32":
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        ) as key:
            if enable:
                formatted_path = f'"{Path(app_path).resolve()}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, formatted_path)
                logger.info("Enabled autostart on Windows for '%s'", app_name)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info("Disabled autostart on Windows for '%s'", app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        logger.warning("Failed to configure Windows autostart: %s", e)
        return False


def set_autostart_macos(bundle_id: str, app_path: str, enable: bool) -> bool:
    """Create or remove macOS LaunchAgent plist for login autostart."""
    if sys.platform != "darwin":
        return False

    try:
        agents_dir = Path.home() / "Library" / "LaunchAgents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        plist_path = agents_dir / f"{bundle_id}.plist"

        if enable:
            content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{bundle_id}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{Path(app_path).resolve()}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>"""
            plist_path.write_text(content, encoding="utf-8")
            logger.info("Enabled LaunchAgent autostart on macOS for '%s'", bundle_id)
        else:
            if plist_path.is_file():
                plist_path.unlink(missing_ok=True)
                logger.info("Disabled LaunchAgent autostart on macOS for '%s'", bundle_id)
        return True
    except Exception as e:
        logger.warning("Failed to configure macOS autostart: %s", e)
        return False


def sync_autostart(
    app_name: str,
    organization_name: str,
    enable: bool,
    executable_path: str | None = None,
) -> bool:
    """Synchronize the OS autostart configuration with the application settings."""
    target_path = executable_path or sys.executable

    if sys.platform == "win32":
        return set_autostart_windows(app_name, target_path, enable)
    elif sys.platform == "darwin":
        bundle_id = f"com.{organization_name.lower().replace(' ', '')}.{app_name.lower().replace(' ', '')}"
        return set_autostart_macos(bundle_id, target_path, enable)
    return False
