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

    if parsed.username or parsed.password:
        return False
    if (scheme == "http" and not config.allow_insecure_http
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}):
        return False

    return config.is_host_allowed(parsed.hostname or "")


def is_external_url_allowed(url: str, config: AppConfig) -> bool:
    try:
        parsed = urlparse(url)
        return bool(
            parsed.hostname
            and not parsed.username
            and not parsed.password
            and (parsed.scheme == "https" or (
                parsed.scheme == "http" and (config.allow_insecure_http or
                    parsed.hostname in {"localhost", "127.0.0.1", "::1"})
            ))
        )
    except ValueError:
        return False
