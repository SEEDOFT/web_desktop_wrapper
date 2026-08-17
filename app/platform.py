from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

BrowserBackend = Literal["edgechromium", "cocoa"]
BrowserRenderer = Literal["edgechromium", "wkwebview"]


def platform_name(value: str | None = None) -> str:
    return value or sys.platform


def browser_backend(value: str | None = None) -> BrowserBackend:
    current = platform_name(value)
    if current == "win32":
        return "edgechromium"
    if current == "darwin":
        return "cocoa"
    raise RuntimeError("This application supports Windows and macOS only.")


def runtime_check_required(value: str | None = None) -> bool:
    return platform_name(value) == "win32"


def renderer_name(value: str | None = None) -> BrowserRenderer:
    current = platform_name(value)
    if current == "win32":
        return "edgechromium"
    if current == "darwin":
        return "wkwebview"
    raise RuntimeError("This application supports Windows and macOS only.")


def persistent_storage_path(
    organization: str,
    profile: str,
    value: str | None = None,
    home: Path | None = None,
) -> Path:
    current = platform_name(value)
    user_home = home or Path.home()
    if current == "darwin":
        return (
            user_home
            / "Library"
            / "Application Support"
            / organization
            / profile
            / "WebKit"
        )
    if current == "win32":
        return user_home / "AppData" / "Local" / organization / profile / "WebView2"
    raise RuntimeError("This application supports Windows and macOS only.")
