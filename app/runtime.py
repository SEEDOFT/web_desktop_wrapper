from __future__ import annotations

import os
from dataclasses import dataclass


WEBVIEW2_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    available: bool
    version: str | None = None


def find_webview2_runtime() -> RuntimeStatus:
    """Detect the Evergreen WebView2 Runtime from Microsoft's registry keys."""
    if os.name != "nt":
        return RuntimeStatus(False)

    import winreg

    paths = (
        rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}",
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}",
    )
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)

    access_modes = [winreg.KEY_READ]
    if hasattr(winreg, "KEY_WOW64_32KEY"):
        access_modes.append(winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access_modes.append(winreg.KEY_READ | winreg.KEY_WOW64_64KEY)

    for root in roots:
        for path in paths:
            for access in access_modes:
                try:
                    with winreg.OpenKey(root, path, 0, access) as key:
                        version, _ = winreg.QueryValueEx(key, "pv")
                except (FileNotFoundError, OSError):
                    continue

                normalized = str(version).strip()
                if normalized and normalized != "0.0.0.0":
                    return RuntimeStatus(True, normalized)

    return RuntimeStatus(False)
