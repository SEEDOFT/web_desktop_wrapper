from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import AppConfig, ConfigError, configuration_source


class AppConfigTests(unittest.TestCase):
    def test_stale_embedded_config_does_not_mark_source_as_packaged(self) -> None:
        with patch("app.config.embedded_config.CONFIG", {"wrapper_version": "0.9.0"}), patch(
            "app.config.sys.frozen", False, create=True
        ):
            self.assertEqual(configuration_source(), "development .env")

    def test_packaged_environment_loads_from_memory(self) -> None:
        from app.config import _load_development_environment

        with patch("app.config._is_frozen", return_value=True), patch(
            "app.config.embedded_config.ENV_TEXT",
            "APP_WRAPPER_VERSION=1.0.1\nCUSTOM_SETTING=embedded\n", create=True,
        ), patch.dict(os.environ, {"CUSTOM_SETTING": "external"}, clear=True):
            _load_development_environment()
            self.assertEqual(os.environ["CUSTOM_SETTING"], "embedded")
            self.assertEqual(os.environ["APP_WRAPPER_VERSION"], "1.0.1")

    def setUp(self) -> None:
        patcher = patch("app.config.embedded_config.CONFIG", {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_build_inputs_override_leftover_embedded_configuration(self) -> None:
        with patch("app.config.embedded_config.CONFIG", {
            "wrapper_version": "1.0.0", "web_app_url": "https://old.example.test",
        }), patch.dict(os.environ, {
            "APP_WRAPPER_VERSION": "1.0.1", "WEB_APP_URL": "https://new.example.test",
        }, clear=True):
            config = AppConfig.load(packaged=False)
        self.assertEqual(config.wrapper_version, "1.0.1")
        self.assertEqual(config.web_app_url, "https://new.example.test")

    def test_packaged_version_does_not_require_environment_file(self) -> None:
        with patch("app.config.embedded_config.CONFIG", {
            "wrapper_version": "1.0.1", "web_app_url": "https://portal.example.test",
        }), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(AppConfig.load(packaged=True).wrapper_version, "1.0.1")

    def test_requires_a_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigError):
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
        ), self.assertRaises(ConfigError):
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
        ), self.assertRaises(ConfigError):
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


if __name__ == "__main__":
    unittest.main()
