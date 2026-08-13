from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

from dotenv import load_dotenv

from app import embedded_config


class ConfigError(ValueError):
    """Raised when application configuration is missing, altered, or invalid."""


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _load_development_environment() -> None:
    """Load .env only for source development, never for packaged applications."""
    if _is_frozen():
        return

    candidates = (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    )
    loaded_paths: set[Path] = set()

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            continue

        if resolved in loaded_paths or not resolved.is_file():
            continue

        load_dotenv(dotenv_path=resolved, override=True)
        loaded_paths.add(resolved)


_load_development_environment()


def _embedded_config() -> dict[str, Any]:
    """Return the build-time configuration embedded by tools/build.py."""
    value = getattr(embedded_config, "CONFIG", None)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_web_app_url(url: str) -> str:
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


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "web-desktop"


def _parse_bool(value: Any, default: bool, name: str) -> bool:
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
        f"{name} must be one of: true, false, 1, 0, yes, no, on, off."
    )


def _parse_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer.") from exc

    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return parsed



def _parse_hex_color(value: Any, default: str, name: str) -> str:
    normalized = str(value or default).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", normalized):
        raise ConfigError(f"{name} must use the #RRGGBB format.")
    return normalized.lower()


def _environment_or_embedded(
    environment_name: str,
    embedded: dict[str, Any],
    embedded_name: str,
    default: Any = None,
) -> Any:
    if _is_frozen():
        return embedded.get(embedded_name, default)

    environment_value = os.getenv(environment_name)
    if environment_value is not None:
        return environment_value
    return embedded.get(embedded_name, default)


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str
    organization_name: str
    web_app_url: str
    allowed_hosts: tuple[str, ...]
    allow_subdomains: bool
    open_external_links: bool
    allow_insecure_http: bool
    start_maximized: bool
    window_width: int
    window_height: int
    profile_name: str
    persist_session: bool
    allow_downloads: bool
    production_mode: bool
    page_background_color: str
    app_icon: str

    @classmethod
    def load(cls) -> "AppConfig":
        embedded = _embedded_config()

        app_name = str(
            _environment_or_embedded(
                "APP_NAME",
                embedded,
                "app_name",
                "Web Desktop",
            )
        ).strip() or "Web Desktop"

        organization_name = str(
            _environment_or_embedded(
                "APP_ORGANIZATION",
                embedded,
                "organization_name",
                "WebDesktop",
            )
        ).strip() or "WebDesktop"

        web_app_url = _normalize_web_app_url(
            str(
                _environment_or_embedded(
                    "WEB_APP_URL",
                    embedded,
                    "web_app_url",
                    "",
                )
            )
        )

        allow_insecure_http = _parse_bool(
            _environment_or_embedded(
                "ALLOW_INSECURE_HTTP",
                embedded,
                "allow_insecure_http",
                False,
            ),
            False,
            "ALLOW_INSECURE_HTTP",
        )
        parsed = cls._validate_web_url(web_app_url, allow_insecure_http)

        raw_hosts = _environment_or_embedded(
            "WEB_APP_ALLOWED_HOSTS",
            embedded,
            "allowed_hosts",
            [],
        )
        if isinstance(raw_hosts, str):
            requested_hosts = raw_hosts.split(",")
        elif isinstance(raw_hosts, list):
            requested_hosts = raw_hosts
        else:
            requested_hosts = []

        normalized_hosts = {
            _normalize_host(str(host))
            for host in requested_hosts
            if _normalize_host(str(host))
        }
        normalized_hosts.add(_normalize_host(parsed.hostname or ""))

        allow_subdomains = _parse_bool(
            _environment_or_embedded(
                "ALLOW_SUBDOMAINS",
                embedded,
                "allow_subdomains",
                False,
            ),
            False,
            "ALLOW_SUBDOMAINS",
        )
        open_external_links = _parse_bool(
            _environment_or_embedded(
                "OPEN_EXTERNAL_LINKS",
                embedded,
                "open_external_links",
                False,
            ),
            False,
            "OPEN_EXTERNAL_LINKS",
        )
        start_maximized = _parse_bool(
            _environment_or_embedded(
                "START_MAXIMIZED",
                embedded,
                "start_maximized",
                True,
            ),
            True,
            "START_MAXIMIZED",
        )
        persist_session = _parse_bool(
            _environment_or_embedded(
                "PERSIST_SESSION",
                embedded,
                "persist_session",
                False,
            ),
            False,
            "PERSIST_SESSION",
        )
        allow_downloads = _parse_bool(
            _environment_or_embedded(
                "ALLOW_DOWNLOADS",
                embedded,
                "allow_downloads",
                False,
            ),
            False,
            "ALLOW_DOWNLOADS",
        )

        width = _parse_int(
            _environment_or_embedded(
                "WINDOW_WIDTH",
                embedded,
                "window_width",
                1280,
            ),
            1280,
            800,
            7680,
            "WINDOW_WIDTH",
        )
        height = _parse_int(
            _environment_or_embedded(
                "WINDOW_HEIGHT",
                embedded,
                "window_height",
                800,
            ),
            800,
            600,
            4320,
            "WINDOW_HEIGHT",
        )
        page_background_color = _parse_hex_color(
            _environment_or_embedded(
                "PAGE_BACKGROUND_COLOR",
                embedded,
                "page_background_color",
                "#ffffff",
            ),
            "#ffffff",
            "PAGE_BACKGROUND_COLOR",
        )


        return cls(
            app_name=app_name,
            organization_name=organization_name,
            web_app_url=web_app_url,
            allowed_hosts=tuple(sorted(normalized_hosts)),
            allow_subdomains=allow_subdomains,
            open_external_links=open_external_links,
            allow_insecure_http=allow_insecure_http,
            start_maximized=start_maximized,
            window_width=width,
            window_height=height,
            profile_name=_slugify(f"{organization_name}-{app_name}"),
            persist_session=persist_session,
            allow_downloads=allow_downloads,
            production_mode=_is_frozen(),
            page_background_color=page_background_color,
            app_icon=str(
                _environment_or_embedded(
                    "APP_ICON",
                    embedded,
                    "app_icon",
                    "assets/digi_express.ico",
                )
            ).strip() or "assets/digi_express.ico",
        )

    @staticmethod
    def _validate_web_url(url: str, allow_insecure_http: bool) -> ParseResult:
        if not url:
            raise ConfigError(
                "No web application URL is configured. Set WEB_APP_URL in .env "
                "for development or build the executable with tools/build.py."
            )

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ConfigError("The web application URL must use HTTP or HTTPS.")
        if not parsed.hostname:
            raise ConfigError("The web application URL must contain a valid host.")
        if parsed.username or parsed.password:
            raise ConfigError("Credentials must not be embedded in the web application URL.")

        localhost_hosts = {"localhost", "127.0.0.1", "::1"}
        is_localhost = _normalize_host(parsed.hostname) in localhost_hosts
        if parsed.scheme != "https" and not is_localhost and not allow_insecure_http:
            raise ConfigError("Remote web applications must use HTTPS.")

        return parsed

    def is_host_allowed(self, host: str) -> bool:
        normalized = _normalize_host(host)
        if not normalized:
            return False

        for allowed in self.allowed_hosts:
            if normalized == allowed:
                return True
            if self.allow_subdomains and normalized.endswith(f".{allowed}"):
                return True

        return False
