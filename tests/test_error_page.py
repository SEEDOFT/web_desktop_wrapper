from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.browser import _navigation_error_html, _should_show_navigation_error
from app.config import AppConfig


class ErrorPageDecisionTests(unittest.TestCase):
    def test_successful_navigation_shows_no_error_page(self) -> None:
        self.assertFalse(_should_show_navigation_error(True, None))
        self.assertFalse(_should_show_navigation_error(True, 6))

    def test_genuine_failures_show_error_page(self) -> None:
        self.assertTrue(_should_show_navigation_error(False, None))
        self.assertTrue(_should_show_navigation_error(False, 6))
        self.assertTrue(_should_show_navigation_error(False, 12))

    def test_cancelled_navigation_does_not_show_error_page(self) -> None:
        self.assertFalse(_should_show_navigation_error(False, 14))
        self.assertFalse(_should_show_navigation_error(False, "14"))

    def test_unparseable_status_still_shows_error_page(self) -> None:
        self.assertTrue(_should_show_navigation_error(False, "not-a-number"))


class ErrorPageContentTests(unittest.TestCase):
    def _config(self) -> AppConfig:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test/login",
                "APP_NAME": "Digi Express",
            },
            clear=True,
        ):
            return AppConfig.load()

    def test_error_page_is_branded(self) -> None:
        html = _navigation_error_html(self._config())
        self.assertIn("Digi Express", html)
        self.assertIn("could not be reached", html)

    def test_error_page_hides_the_web_app_url(self) -> None:
        html = _navigation_error_html(self._config())
        self.assertNotIn("portal.example.test", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("login", html)

    def test_error_page_contains_retry_button_and_shortcut_hint(self) -> None:
        html = _navigation_error_html(self._config())
        self.assertIn("Retry Connection", html)
        self.assertIn("retryConnection", html)
        self.assertIn("Ctrl+R", html)
        self.assertIn("F5", html)


if __name__ == "__main__":
    unittest.main()
