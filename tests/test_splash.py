from __future__ import annotations

import unittest
from unittest.mock import patch
import os

from app.config import AppConfig
from app.splash import (
    SPLASH_BACKGROUND,
    generate_splash_html,
    _load_splash_logo_data_uri,
)


class SplashTests(unittest.TestCase):
    def test_splash_background_is_valid_hex(self) -> None:
        self.assertTrue(SPLASH_BACKGROUND.startswith("#"))
        self.assertEqual(len(SPLASH_BACKGROUND), 7)

    def test_load_splash_logo_data_uri(self) -> None:
        data_uri = _load_splash_logo_data_uri()
        self.assertTrue(data_uri.startswith("data:"))
        self.assertIn("base64,", data_uri)

    def test_load_splash_logo_nonexistent_path_falls_back(self) -> None:
        data_uri = _load_splash_logo_data_uri("/nonexistent/logo.png")
        self.assertTrue(data_uri.startswith("data:"))

    def test_generate_splash_html_structure(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        html_content = generate_splash_html(config)
        self.assertIn("<!doctype html>", html_content)
        self.assertIn(config.app_name, html_content)

    def test_generate_splash_html_animations(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        html_content = generate_splash_html(config)
        self.assertIn("frame-breathe", html_content)
        self.assertIn("aura-breathe", html_content)
        self.assertIn("logo-glow", html_content)
        self.assertIn("halo-expand", html_content)
        self.assertIn("dot-pulse", html_content)

    def test_generate_splash_html_dissolve(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        html_content = generate_splash_html(config)
        self.assertIn("dissolve", html_content)
        self.assertIn("window.fadeOut", html_content)

    def test_generate_splash_html_background_matches(self) -> None:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            config = AppConfig.load()

        html_content = generate_splash_html(config)
        # The CSS background must include SPLASH_BACKGROUND for seamless
        # transition with the native window chrome
        self.assertIn(SPLASH_BACKGROUND, html_content)


if __name__ == "__main__":
    unittest.main()
