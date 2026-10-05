from __future__ import annotations

import ctypes
import os
import sys


def _enable_per_monitor_dpi_awareness() -> None:
    """Enable sharp per-monitor rendering before WinForms/WebView2 initializes."""
    if os.name != "nt":
        return

    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)
        )
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


_enable_per_monitor_dpi_awareness()
if sys.platform == "win32":
    os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium")
elif sys.platform == "darwin":
    os.environ.setdefault("PYWEBVIEW_GUI", "cocoa")

from app.main import run

if __name__ == "__main__":
    raise SystemExit(run())
