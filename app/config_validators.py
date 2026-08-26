"""Configuration validation helpers for application settings.

This module provides reusable validation and parsing functions to reduce
boilerplate and improve consistency in configuration handling.
"""

import os
import re
from typing import Any, TypeVar

from app.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ConfigError(ValueError):
    """Raised when application configuration is missing, altered, or invalid."""


def get_config_value(
    environment_name: str,
    embedded: dict[str, Any],
    embedded_name: str,
    default: Any = None,
    is_frozen: bool = False,
) -> Any:
    """Get a configuration value from environment or embedded config.
    
    Args:
        environment_name: Environment variable name to check
        embedded: Dictionary of embedded configuration values
        embedded_name: Key name in embedded config dictionary
        default: Default value if not found
        is_frozen: Whether application is frozen/packaged
    
    Returns:
        Configuration value from environment (if not frozen), embedded config,
        or default value (in that order of precedence).
    """
    if is_frozen:
        return embedded.get(embedded_name, default)

    environment_value = os.getenv(environment_name)
    if environment_value is not None:
        return environment_value
    return embedded.get(embedded_name, default)


def parse_string(
    value: Any,
    default: str = "",
    name: str = "value",
    pattern: str | None = None,
    pattern_name: str | None = None,
) -> str:
    """Parse and validate a string configuration value.
    
    Args:
        value: Value to parse
        default: Default if value is None or empty
        name: Configuration name for error messages
        pattern: Optional regex pattern that value must match
        pattern_name: Description of pattern for error messages
    
    Returns:
        Parsed string value
    
    Raises:
        ConfigError: If value doesn't match pattern (if provided)
    """
    normalized = str(value or default).strip()
    
    if pattern and not re.fullmatch(pattern, normalized):
        raise ConfigError(
            f"{name} must {pattern_name or f'match pattern {pattern}'}"
        )
    
    return normalized or default


def parse_bool(
    value: Any,
    default: bool = False,
    name: str = "value",
) -> bool:
    """Parse and validate a boolean configuration value.
    
    Args:
        value: Value to parse (None, bool, str, int)
        default: Default if value is None or empty
        name: Configuration name for error messages
    
    Returns:
        Parsed boolean value
    
    Raises:
        ConfigError: If string value is not a recognized boolean representation
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ConfigError(
        f"{name} must be one of: true, false, 1, 0, yes, no, on, off"
    )


def parse_int(
    value: Any,
    default: int = 0,
    minimum: int | None = None,
    maximum: int | None = None,
    name: str = "value",
) -> int:
    """Parse and validate an integer configuration value.
    
    Args:
        value: Value to parse
        default: Default if value is None or empty
        minimum: Minimum allowed value (inclusive)
        maximum: Maximum allowed value (inclusive)
        name: Configuration name for error messages
    
    Returns:
        Parsed integer value
    
    Raises:
        ConfigError: If value is not a valid integer or outside bounds
    """
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer") from exc

    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ConfigError(f"{name} must be at most {maximum}")
    
    return parsed


def parse_hex_color(
    value: Any,
    default: str = "#ffffff",
    name: str = "color",
) -> str:
    """Parse and validate a hex color value (#RRGGBB format).
    
    Args:
        value: Value to parse
        default: Default if value is None
        name: Configuration name for error messages
    
    Returns:
        Normalized hex color in lowercase
    
    Raises:
        ConfigError: If value is not a valid hex color
    """
    normalized = str(value or default).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", normalized):
        raise ConfigError(f"{name} must use #RRGGBB format (e.g., #ffffff)")
    return normalized.lower()


def parse_url_list(
    value: Any,
    default: list[str] | None = None,
) -> list[str]:
    """Parse a list of URLs from string or list.
    
    Args:
        value: Value to parse (comma-separated string or list)
        default: Default if value is None or empty
    
    Returns:
        List of URL strings
    """
    if default is None:
        default = []
    
    if isinstance(value, str):
        hosts = [h.strip() for h in value.split(",")]
        return [h for h in hosts if h]
    elif isinstance(value, list):
        return [str(h).strip() for h in value if h]
    
    return default


def normalize_host(host: str) -> str:
    """Normalize a hostname for comparison.
    
    Args:
        host: Hostname to normalize
    
    Returns:
        Lowercase hostname with trailing dot removed
    """
    return host.strip().lower().rstrip(".")


def normalize_web_app_url(url: str) -> str:
    """Normalize a web application URL.
    
    Automatically adds http:// scheme to localhost URLs without scheme.
    
    Args:
        url: URL to normalize
    
    Returns:
        Normalized URL
    """
    normalized = url.strip()

    local_without_scheme = re.fullmatch(
        r"(?P<host>localhost|127\.0\.0\.1|\[::1\])"
        r"(?P<port>:\d{1,5})?"
        r"(?P<path>/.*)?",
        normalized,
        flags=re.IGNORECASE,
    )
    if local_without_scheme:
        normalized = f"http://{normalized}"

    return normalized


def slugify(value: str) -> str:
    """Convert a string to a slug suitable for filenames/identifiers.
    
    Args:
        value: String to slugify
    
    Returns:
        Slugified string (lowercase, hyphens for separators)
    """
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "web-desktop"
