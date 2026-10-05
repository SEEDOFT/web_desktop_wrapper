from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)


def _resolve_scripts_dir() -> Path:
    """Resolve the directory containing standalone JavaScript files."""
    # PyInstaller unpacked temp directory
    if hasattr(sys, "_MEIPASS"):
        runtime_sys: Any = sys
        meipass = Path(runtime_sys._MEIPASS)
        for candidate in (
            meipass / "app" / "scripts",
            meipass / "scripts",
        ):
            if candidate.is_dir():
                return candidate

    # Normal directory relative to this module
    module_dir = Path(__file__).resolve().parent / "scripts"
    if module_dir.is_dir():
        return module_dir

    # Fallback paths (CWD, executable parent)
    for candidate in (
        Path.cwd() / "app" / "scripts",
        Path.cwd() / "scripts",
        Path(sys.executable).resolve().parent / "app" / "scripts",
        Path(sys.executable).resolve().parent / "scripts",
    ):
        if candidate.is_dir():
            return candidate

    return Path.cwd() / "app" / "scripts"


@lru_cache(maxsize=32)
def _read_script_file(file_name: str) -> str:
    """Read a script file from the scripts directory with caching."""
    scripts_dir = _resolve_scripts_dir()
    script_path = scripts_dir / file_name
    if not script_path.is_file():
        logger.debug("Script file not found: %s", script_path)
        return ""
    try:
        return script_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to read script file %s: %s", script_path, exc)
        return ""


def get_script(file_name: str, **replacements: Any) -> str:
    """Retrieve a standalone JavaScript script and apply template replacements."""
    content = _read_script_file(file_name)
    if not content:
        return ""

    for key, value in replacements.items():
        placeholder = f"{{{{{key}}}}}"
        content = content.replace(placeholder, str(value))

    return content
