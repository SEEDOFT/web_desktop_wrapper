from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from app.browser import _attach_wrapper_version_header, _navigation_toolbar_layout
from app.config import AppConfig
from app.navigation import is_navigation_allowed


class NavigationTests(unittest.TestCase):
    def _config(self) -> AppConfig:
        with patch.dict(
            os.environ,
            {"WEB_APP_URL": "https://portal.example.test"},
            clear=True,
        ):
            return AppConfig.load(packaged=False)

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

    def test_blocks_https_downgrade_and_credentials(self) -> None:
        config = self._config()
        self.assertFalse(is_navigation_allowed("http://portal.example.test/", config))
        self.assertFalse(is_navigation_allowed("https://user:password@portal.example.test/", config))

    def test_toolbar_layout_uses_non_overlapping_container(self) -> None:
        layout = _navigation_toolbar_layout()

        self.assertEqual(layout["toolbar_dock"], "Top")
        self.assertEqual(layout["content_panel_dock"], "Fill")
        self.assertEqual(layout["host_container_dock"], "Fill")

    def test_native_request_header_helper_covers_get_and_post_on_windows(self) -> None:
        config = self._config()
        for method in ("GET", "POST"):
            request: Any = type("Request", (), {
                "url": "https://portal.example.test/login",
                "method": method,
                "headers": {},
            })()
            _attach_wrapper_version_header(request, config)
            self.assertEqual(request.headers, {"X-Wrapper-Version": "1.0.0"})

    def test_native_navigation_header_is_scoped_to_approved_web_urls(self) -> None:
        config = self._config()
        for url in ("https://evil.example.test/", "file:///tmp/private"):
            request: Any = type("Request", (), {"url": url, "headers": {}})()
            _attach_wrapper_version_header(request, config)
            self.assertEqual(request.headers, {})



if __name__ == "__main__":
    unittest.main()
