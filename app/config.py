from __future__ import annotations

import os
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

from dotenv import load_dotenv

from app import embedded_config
from app.config_validators import (
    ConfigError,
    get_config_value,
    normalize_host,
    normalize_web_app_url,
    parse_bool,
    parse_hex_color,
    parse_int,
    parse_url_list,
    slugify,
)
from app.runtime_mode import is_packaged


def _is_frozen() -> bool:
    return is_packaged()


def configuration_source() -> str:
    """Return a safe description of the active configuration source."""
    return "embedded environment" if _is_frozen() else "development .env"


def _load_development_environment() -> None:
    """Load .env only for source development, never for packaged applications."""
    if _is_frozen():
        content = getattr(embedded_config, "ENV_TEXT", "")
        if content:
            load_dotenv(stream=StringIO(content), override=True)
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
    single_instance: bool
    show_splash: bool
    splash_duration: float
    enable_tray: bool
    minimize_to_tray: bool
    default_downloads_path: str
    show_download_notifications: bool
    user_agent: str
    browser_locale: str
    run_on_startup: bool
    allow_file_drop: bool
    wrapper_version: str = "1.0.0"

    @classmethod
    def load(cls, *, packaged: bool | None = None) -> AppConfig:
        embedded = _embedded_config()
        is_frozen = _is_frozen() if packaged is None else packaged
        if packaged is False:
            embedded = {}

        app_name = str(
            get_config_value(
                "APP_NAME",
                embedded,
                "app_name",
                "Web Desktop",
                is_frozen=is_frozen,
            )
        ).strip() or "Web Desktop"

        organization_name = str(
            get_config_value(
                "APP_ORGANIZATION",
                embedded,
                "organization_name",
                "WebDesktop",
                is_frozen=is_frozen,
            )
        ).strip() or "WebDesktop"

        web_app_url = normalize_web_app_url(
            str(
                get_config_value(
                    "WEB_APP_URL",
                    embedded,
                    "web_app_url",
                    "",
                    is_frozen=is_frozen,
                )
            )
        )

        allow_insecure_http = parse_bool(
            get_config_value(
                "ALLOW_INSECURE_HTTP",
                embedded,
                "allow_insecure_http",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="ALLOW_INSECURE_HTTP",
        )
        parsed = cls._validate_web_url(web_app_url, allow_insecure_http)

        raw_hosts = get_config_value(
            "WEB_APP_ALLOWED_HOSTS",
            embedded,
            "allowed_hosts",
            [],
            is_frozen=is_frozen,
        )
        requested_hosts = parse_url_list(raw_hosts)

        normalized_hosts = {
            normalize_host(str(host))
            for host in requested_hosts
            if normalize_host(str(host))
        }
        normalized_hosts.add(normalize_host(parsed.hostname or ""))

        allow_subdomains = parse_bool(
            get_config_value(
                "ALLOW_SUBDOMAINS",
                embedded,
                "allow_subdomains",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="ALLOW_SUBDOMAINS",
        )
        open_external_links = parse_bool(
            get_config_value(
                "OPEN_EXTERNAL_LINKS",
                embedded,
                "open_external_links",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="OPEN_EXTERNAL_LINKS",
        )
        start_maximized = parse_bool(
            get_config_value(
                "START_MAXIMIZED",
                embedded,
                "start_maximized",
                True,
                is_frozen=is_frozen,
            ),
            default=True,
            name="START_MAXIMIZED",
        )
        persist_session = parse_bool(
            get_config_value(
                "PERSIST_SESSION",
                embedded,
                "persist_session",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="PERSIST_SESSION",
        )
        allow_downloads = parse_bool(
            get_config_value(
                "ALLOW_DOWNLOADS",
                embedded,
                "allow_downloads",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="ALLOW_DOWNLOADS",
        )
        single_instance = parse_bool(
            get_config_value(
                "SINGLE_INSTANCE",
                embedded,
                "single_instance",
                True,
                is_frozen=is_frozen,
            ),
            default=True,
            name="SINGLE_INSTANCE",
        )
        show_splash = parse_bool(
            get_config_value(
                "SHOW_SPLASH",
                embedded,
                "show_splash",
                True,
                is_frozen=is_frozen,
            ),
            default=True,
            name="SHOW_SPLASH",
        )

        try:
            raw_duration = get_config_value(
                "SPLASH_DURATION",
                embedded,
                "splash_duration",
                4.5,
                is_frozen=is_frozen,
            )
            splash_duration = float(raw_duration)
        except (TypeError, ValueError):
            splash_duration = 4.5

        enable_tray = parse_bool(
            get_config_value(
                "ENABLE_SYSTEM_TRAY",
                embedded,
                "enable_tray",
                True,
                is_frozen=is_frozen,
            ),
            default=True,
            name="ENABLE_SYSTEM_TRAY",
        )
        minimize_to_tray = parse_bool(
            get_config_value(
                "MINIMIZE_TO_TRAY",
                embedded,
                "minimize_to_tray",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="MINIMIZE_TO_TRAY",
        )
        default_downloads_path = str(
            get_config_value(
                "DEFAULT_DOWNLOADS_PATH",
                embedded,
                "default_downloads_path",
                "",
                is_frozen=is_frozen,
            )
        ).strip()
        show_download_notifications = parse_bool(
            get_config_value(
                "SHOW_DOWNLOAD_NOTIFICATIONS",
                embedded,
                "show_download_notifications",
                True,
                is_frozen=is_frozen,
            ),
            default=True,
            name="SHOW_DOWNLOAD_NOTIFICATIONS",
        )
        user_agent = str(
            get_config_value(
                "USER_AGENT",
                embedded,
                "user_agent",
                "",
                is_frozen=is_frozen,
            )
        ).strip()
        browser_locale = str(
            get_config_value(
                "BROWSER_LOCALE",
                embedded,
                "browser_locale",
                "",
                is_frozen=is_frozen,
            )
        ).strip()
        run_on_startup = parse_bool(
            get_config_value(
                "RUN_ON_STARTUP",
                embedded,
                "run_on_startup",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="RUN_ON_STARTUP",
        )
        allow_file_drop = parse_bool(
            get_config_value(
                "ALLOW_FILE_DROP",
                embedded,
                "allow_file_drop",
                False,
                is_frozen=is_frozen,
            ),
            default=False,
            name="ALLOW_FILE_DROP",
        )

        width = parse_int(
            get_config_value(
                "WINDOW_WIDTH",
                embedded,
                "window_width",
                1280,
                is_frozen=is_frozen,
            ),
            default=1280,
            minimum=800,
            maximum=7680,
            name="WINDOW_WIDTH",
        )
        height = parse_int(
            get_config_value(
                "WINDOW_HEIGHT",
                embedded,
                "window_height",
                800,
                is_frozen=is_frozen,
            ),
            default=800,
            minimum=600,
            maximum=4320,
            name="WINDOW_HEIGHT",
        )
        page_background_color = parse_hex_color(
            get_config_value(
                "PAGE_BACKGROUND_COLOR",
                embedded,
                "page_background_color",
                "#ffffff",
                is_frozen=is_frozen,
            ),
            default="#ffffff",
            name="PAGE_BACKGROUND_COLOR",
        )

        wrapper_version = str(
            get_config_value(
                "APP_WRAPPER_VERSION",
                embedded,
                "wrapper_version",
                os.getenv("WRAPPER_VERSION", "1.0.0"),
                is_frozen=is_frozen,
            )
        ).strip() or "1.0.0"

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
            profile_name=slugify(f"{organization_name}-{app_name}"),
            persist_session=persist_session,
            allow_downloads=allow_downloads,
            production_mode=is_frozen,
            page_background_color=page_background_color,
            app_icon=str(
                get_config_value(
                    "APP_ICON",
                    embedded,
                    "app_icon",
                    "assets/digi_express.ico",
                    is_frozen=is_frozen,
                )
            ).strip() or "assets/digi_express.ico",
            single_instance=single_instance,
            show_splash=show_splash,
            splash_duration=splash_duration,
            enable_tray=enable_tray,
            minimize_to_tray=minimize_to_tray,
            default_downloads_path=default_downloads_path,
            show_download_notifications=show_download_notifications,
            user_agent=user_agent,
            browser_locale=browser_locale,
            run_on_startup=run_on_startup,
            allow_file_drop=allow_file_drop,
            wrapper_version=wrapper_version,
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
        is_localhost = normalize_host(parsed.hostname) in localhost_hosts
        if parsed.scheme != "https" and not is_localhost and not allow_insecure_http:
            raise ConfigError("Remote web applications must use HTTPS.")

        return parsed

    def is_host_allowed(self, host: str) -> bool:
        normalized = normalize_host(host)
        if not normalized:
            return False

        for allowed in self.allowed_hosts:
            if normalized == allowed:
                return True
            if self.allow_subdomains and normalized.endswith(f".{allowed}"):
                return True

        return False
