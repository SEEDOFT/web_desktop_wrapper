from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import AppConfig, ConfigError


class AppConfigTests(unittest.TestCase):
    def test_requires_a_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                AppConfig.load()

    def test_accepts_https_and_exact_host(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test/login"},
            clear=True,
        ):
            config = AppConfig.load()

        self.assertTrue(config.is_host_allowed("portal.example.test"))
        self.assertFalse(config.is_host_allowed("api.portal.example.test"))
        self.assertFalse(config.is_host_allowed("example.test.evil.invalid"))

    def test_normalizes_localhost_without_scheme(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "localhost:8000"},
            clear=True,
        ):
            config = AppConfig.load()

        self.assertEqual(config.web_app_url, "http://localhost:8000")
        self.assertTrue(config.is_host_allowed("localhost"))

    def test_rejects_remote_http_by_default(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "http://portal.example.test"},
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                AppConfig.load()

    def test_allows_localhost_http(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "http://127.0.0.1:8000"},
            clear=True,
        ):
            config = AppConfig.load()

        self.assertEqual(config.web_app_url, "http://127.0.0.1:8000")

    def test_can_enable_subdomain_navigation(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "ALLOW_SUBDOMAINS": "true",
            },
            clear=True,
        ):
            config = AppConfig.load()

        self.assertTrue(config.is_host_allowed("api.portal.example.test"))

    def test_hardened_defaults_disable_persistence_and_downloads(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        self.assertFalse(config.persist_session)
        self.assertFalse(config.allow_downloads)
        self.assertFalse(config.open_external_links)

    def test_rendering_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        self.assertEqual(config.page_background_color, "#ffffff")

    def test_rejects_invalid_background_color(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "PAGE_BACKGROUND_COLOR": "white",
            },
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                AppConfig.load()

    def test_wrapper_version_default_and_custom(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()
            self.assertEqual(config.wrapper_version, "1.0.0")

        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "APP_WRAPPER_VERSION": "2.4.0",
            },
            clear=True,
        ):
            config = AppConfig.load()
            self.assertEqual(config.wrapper_version, "2.4.0")

    def test_embedded_webview_default_and_custom(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()
            self.assertTrue(config.embedded_webview)

        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "EMBEDDED_WEBVIEW": "false",
            },
            clear=True,
        ):
            config = AppConfig.load()
            self.assertFalse(config.embedded_webview)

        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "EMBED_WEBVIEW": "false",
            },
            clear=True,
        ):
            config = AppConfig.load()
            self.assertFalse(config.embedded_webview)


if __name__ == "__main__":
    unittest.main()
