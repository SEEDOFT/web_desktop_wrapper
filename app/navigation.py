from __future__ import annotations

from urllib.parse import urlparse

from app.config import AppConfig


_INTERNAL_SCHEMES = {"about", "blob", "data"}


def is_navigation_allowed(url: str, config: AppConfig) -> bool:
    """Allow internal documents and top-level HTTP(S) navigation to trusted hosts."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    scheme = parsed.scheme.lower()
    if scheme in _INTERNAL_SCHEMES:
        return True

    if scheme not in {"http", "https"}:
        return False

    return config.is_host_allowed(parsed.hostname or "")
