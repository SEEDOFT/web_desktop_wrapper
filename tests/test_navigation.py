from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import AppConfig
from app.navigation import is_navigation_allowed
from app.browser import _navigation_toolbar_layout


class NavigationTests(unittest.TestCase):
    def _config(self) -> AppConfig:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            return AppConfig.load()

    def test_allows_configured_host(self) -> None:
        config = self._config()
        self.assertTrue(
            is_navigation_allowed(
                "https://portal.example.test/dashboard",
                config,
            )
        )

    def test_blocks_similar_malicious_host(self) -> None:
        config = self._config()
        self.assertFalse(
            is_navigation_allowed(
                "https://portal.example.test.evil.invalid/",
                config,
            )
        )

    def test_blocks_unapproved_subdomain_by_default(self) -> None:
        config = self._config()
        self.assertFalse(
            is_navigation_allowed(
                "https://api.portal.example.test/",
                config,
            )
        )

    def test_allows_internal_webview_documents(self) -> None:
        config = self._config()
        self.assertTrue(is_navigation_allowed("about:blank", config))
        self.assertTrue(is_navigation_allowed("data:text/plain,ok", config))

    def test_blocks_non_web_schemes(self) -> None:
        config = self._config()
        self.assertFalse(is_navigation_allowed("file:///C:/secret.txt", config))
        self.assertFalse(is_navigation_allowed("javascript:alert(1)", config))

    def test_toolbar_layout_uses_non_overlapping_container(self) -> None:
        layout = _navigation_toolbar_layout()

        self.assertEqual(layout["toolbar_dock"], "Top")
        self.assertEqual(layout["content_panel_dock"], "Fill")
        self.assertEqual(layout["host_container_dock"], "Fill")



if __name__ == "__main__":
    unittest.main()
