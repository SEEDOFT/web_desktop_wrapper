"""Packaged runtime detection without importing configuration or logging."""
from __future__ import annotations

import sys


def is_packaged() -> bool:
    return bool(
        getattr(sys, "frozen", False)
        or hasattr(sys, "__nuitka_version__")
        or hasattr(sys, "nuitka_version")
        or "__compiled__" in globals()
    )
