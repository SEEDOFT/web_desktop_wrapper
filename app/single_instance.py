from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)


class SingleInstanceLock:
    """Manages single-instance lifecycle and resource cleanup."""

    def __init__(self, handle: Any, is_windows: bool, lock_path: Path | None = None) -> None:
        self._handle = handle
        self._is_windows = is_windows
        self._lock_path = lock_path

    def release(self) -> None:
        """Release lock handle and clean up files."""
        if self._is_windows:
            if self._handle:
                try:
                    import ctypes
                    windll = getattr(ctypes, "windll", None)
                    if windll is not None:
                        windll.kernel32.CloseHandle(self._handle)
                except Exception as e:
                    logger.debug("Failed to close single instance mutex handle: %s", e)
                self._handle = None
        else:
            if self._handle:
                try:
                    import fcntl
                    fcntl_mod: Any = fcntl
                    fcntl_mod.flock(self._handle.fileno(), fcntl_mod.LOCK_UN)
                    self._handle.close()
                except Exception as e:
                    logger.debug("Failed to release file lock: %s", e)
                self._handle = None
            if self._lock_path and self._lock_path.exists():
                try:
                    self._lock_path.unlink()
                except Exception as e:
                    logger.debug("Failed to remove lock file: %s", e)


def activate_existing_window(app_title: str) -> None:
    """Bring an already running instance of the application to the foreground."""
    if sys.platform == "win32":
        try:
            import ctypes
            windll = getattr(ctypes, "windll", None)
            if windll is not None:
                user32 = windll.user32
                # Find window by title
                hwnd = user32.FindWindowW(None, app_title)
                if hwnd:
                    # SW_RESTORE = 9, SW_SHOW = 5
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    logger.info("Activated existing window '%s'", app_title)
        except Exception as e:
            logger.debug("Failed to activate existing Windows window: %s", e)
    elif sys.platform == "darwin":
        try:
            import subprocess
            # Use AppleScript to activate application by name
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "{app_title}" to activate',
                ],
                check=False,
                capture_output=True,
            )
            logger.info("Activated existing macOS application '%s'", app_title)
        except Exception as e:
            logger.debug("Failed to activate existing macOS app: %s", e)


def acquire_single_instance(app_id: str, app_title: str) -> SingleInstanceLock | None:
    """Attempt to acquire a single-instance lock.

    Returns:
        SingleInstanceLock if this is the only running instance,
        or None if another instance is already running.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return None
            kernel32 = windll.kernel32
            # Create a unique named mutex for the application
            mutex_name = f"Local\\WebDesktopWrapper_{app_id}"
            mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            # ERROR_ALREADY_EXISTS = 183
            if last_error == 183:
                logger.info("Another instance is already running (mutex %s)", mutex_name)
                activate_existing_window(app_title)
                if mutex:
                    kernel32.CloseHandle(mutex)
                return None
            return SingleInstanceLock(handle=mutex, is_windows=True)
        except Exception as e:
            logger.warning("Single instance check failed on Windows: %s", e)
            return None

    # POSIX / macOS
    try:
        import fcntl
        fcntl_mod: Any = fcntl
        lock_dir = Path(tempfile.gettempdir())
        lock_file = lock_dir / f"webdesktop_{app_id}.lock"
        handle = open(lock_file, "a+")
        try:
            fcntl_mod.flock(handle.fileno(), fcntl_mod.LOCK_EX | fcntl_mod.LOCK_NB)
            return SingleInstanceLock(handle=handle, is_windows=False, lock_path=lock_file)
        except (BlockingIOError, OSError):
            logger.info("Another instance is already running (lockfile %s)", lock_file)
            activate_existing_window(app_title)
            handle.close()
            return None
    except Exception as e:
        logger.warning("Single instance check failed on POSIX/macOS: %s", e)
        return None
