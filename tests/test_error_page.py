from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.browser import (
    _attach_error_page_handler,
    _navigation_error_html,
    _should_show_navigation_error,
    _startup_watchdog,
    _UnreachablePageActions,
)
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
    def test_startup_timeout_uses_allowed_internal_base_url(self) -> None:
        window = MagicMock()
        ready = MagicMock()
        ready.wait.return_value = False
        with patch("app.browser._show_first_frame"):
            _startup_watchdog(window, ready, self._config(), timeout_seconds=1)
        self.assertEqual(window.load_html.call_args.kwargs["base_uri"], "about:blank")
        self.assertIn("wdw-unreachable-page", window.load_html.call_args.args[0])

    def test_error_actions_retry_approved_destination_and_close_local_document(self) -> None:
        window = MagicMock()
        window.evaluate_js.return_value = True
        window._wdw_retry_url = "https://portal.example.test/detail"
        actions = _UnreachablePageActions(window, self._config())
        self.assertEqual(actions.refresh_unreachable_page(), window._wdw_retry_url)
        window.load_url.assert_not_called()
        with patch("app.browser.threading.Thread") as worker:
            self.assertTrue(actions.close_unreachable_page())
            worker.return_value.start.assert_called_once_with()
        window.events.closed.is_set.return_value = False
        actions._close_after_acknowledgment()
        window.destroy.assert_called_once_with()

    def test_remote_pages_cannot_use_error_actions(self) -> None:
        window = MagicMock()
        window.evaluate_js.return_value = False
        actions = _UnreachablePageActions(window, self._config())
        self.assertFalse(actions.refresh_unreachable_page())
        self.assertFalse(actions.close_unreachable_page())
        window.load_url.assert_not_called()
        window.destroy.assert_not_called()

    def test_windows_completion_clears_progress_without_replacing_canceled_page(self) -> None:
        class Event:
            def __init__(self) -> None:
                self.handlers = []

            def __iadd__(self, callback):
                self.handlers.append(callback)
                return self

        core = MagicMock()
        core.Source = "https://portal.example.test/login"
        event = Event()
        core.NavigationCompleted = event
        with patch("app.browser._register_native_handler"):
            _attach_error_page_handler(core, MagicMock(), self._config(), lambda callback: callback(), {})
        event.handlers[0](core, SimpleNamespace(IsSuccess=False, WebErrorStatus=14))
        self.assertIn(".cancel()", core.ExecuteScriptAsync.call_args.args[0])
        core.NavigateToString.assert_not_called()
        event.handlers[0](core, SimpleNamespace(IsSuccess=True))
        self.assertIn(".finish()", core.ExecuteScriptAsync.call_args.args[0])

        window = SimpleNamespace()
        core.NavigationCompleted = Event()
        core.Source = "https://portal.example.test/Detail/CaseSensitive"
        with patch("app.browser._register_native_handler"):
            _attach_error_page_handler(core, MagicMock(), self._config(), lambda callback: callback(), {}, window)
        core.NavigationCompleted.handlers[0](core, SimpleNamespace(IsSuccess=False, WebErrorStatus=6))
        self.assertEqual(window._wdw_retry_url, core.Source)

    def _config(self) -> AppConfig:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test/login",
                "APP_NAME": "Digi Express",
            },
            clear=True,
        ):
            return AppConfig.load(packaged=False)

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
        self.assertIn(">Refresh</button>", html)
        self.assertIn(">Close</button>", html)
        self.assertIn("This site can’t be reached", html)
        self.assertIn("retryConnection", html)
        self.assertIn("Ctrl+R", html)
        self.assertIn("F5", html)
        self.assertNotIn("window.location.reload()", html)


if __name__ == "__main__":
    unittest.main()
