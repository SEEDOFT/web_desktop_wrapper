from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import AppConfig
from app.macos import (
    _copy_request_with_version_header,
    _DecisionHandlerOnce,
    _install_versioned_url_loader,
    _versioned_main_frame_request,
)


class MacOSNavigationTests(unittest.TestCase):
    def test_header_matching_is_case_insensitive_and_replaces_stale_versions(self) -> None:
        request = MagicMock()
        request.URL.return_value.absoluteString.return_value = "https://portal.example.test/login"
        frame = SimpleNamespace(isMainFrame=lambda: True)
        action = SimpleNamespace(targetFrame=lambda: frame, request=lambda: request)
        for name in ("X-Wrapper-Version", "x-wrapper-version", "X-WRAPPER-VERSION"):
            request.allHTTPHeaderFields.return_value = {name: "1.0.1"}
            self.assertIsNone(_versioned_main_frame_request(action, self._config()))
        request.allHTTPHeaderFields.return_value = {"x-wrapper-version": "1.0.0"}
        self.assertIs(_versioned_main_frame_request(action, self._config()), request.mutableCopy.return_value)

    def test_child_frames_and_popups_are_not_replayed_in_main_window(self) -> None:
        request = MagicMock()
        for frame in (None, SimpleNamespace(isMainFrame=lambda: False)):
            action = SimpleNamespace(targetFrame=lambda frame=frame: frame, request=lambda: request)
            self.assertIsNone(_versioned_main_frame_request(action, self._config()))
        request.mutableCopy.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "Requires native Foundation requests")
    def test_real_native_copy_preserves_post_and_cookie_properties(self) -> None:
        from typing import Any

        import Foundation

        native: Any = Foundation
        body = b"csrf=fixture-token&name=hello%20world"
        request = native.NSMutableURLRequest.requestWithURL_(
            native.NSURL.URLWithString_("https://portal.example.test/login")
        )
        request.setHTTPMethod_("POST")
        request.setHTTPBody_(native.NSData.dataWithBytes_length_(body, len(body)))
        request.setValue_forHTTPHeaderField_("application/x-www-form-urlencoded", "Content-Type")
        request.setHTTPShouldHandleCookies_(True)
        copied = _copy_request_with_version_header(request, "1.0.1")
        self.assertEqual(bytes(copied.HTTPBody()), body)
        self.assertEqual(copied.HTTPMethod(), "POST")
        self.assertTrue(copied.HTTPShouldHandleCookies())
        self.assertEqual(copied.valueForHTTPHeaderField_("Content-Type"), "application/x-www-form-urlencoded")
        self.assertEqual(copied.valueForHTTPHeaderField_("X-Wrapper-Version"), "1.0.1")
        self.assertIsNone(request.valueForHTTPHeaderField_("X-Wrapper-Version"))

    def test_native_post_copy_only_changes_version_header(self) -> None:
        mutable_request = MagicMock()
        request = MagicMock()
        request.mutableCopy.return_value = mutable_request

        copied = _copy_request_with_version_header(request, "1.0.1")

        self.assertIs(copied, mutable_request)
        request.mutableCopy.assert_called_once_with()
        mutable_request.setValue_forHTTPHeaderField_.assert_called_once_with(
            "1.0.1", "X-Wrapper-Version"
        )
        mutable_request.setHTTPBody_.assert_not_called()
        mutable_request.setHTTPBodyStream_.assert_not_called()

    def _config(self) -> AppConfig:
        return AppConfig(
            app_name="Test", organization_name="Test", web_app_url="https://portal.example.test",
            allowed_hosts=("portal.example.test",), allow_subdomains=False,
            open_external_links=False, allow_insecure_http=False, start_maximized=False,
            window_width=800, window_height=600, profile_name="test", persist_session=False,
            allow_downloads=False, production_mode=False, page_background_color="#ffffff",
            app_icon="", single_instance=False, show_splash=False, splash_duration=0,
            enable_tray=False, minimize_to_tray=False, default_downloads_path="",
            show_download_notifications=False, user_agent="", browser_locale="",
            run_on_startup=False, allow_file_drop=False, wrapper_version="1.0.1",
        )

    def test_initial_loader_adds_one_version_header_to_approved_url(self) -> None:
        request = MagicMock()
        foundation = SimpleNamespace(
            NSURL=SimpleNamespace(URLWithString_=MagicMock(return_value="native-url")),
            NSMutableURLRequest=SimpleNamespace(requestWithURL_=MagicMock(return_value=request)),
        )
        app_helper = SimpleNamespace(callAfter=lambda callback: callback())
        original = MagicMock()
        browser = SimpleNamespace(
            pywebview_window=SimpleNamespace(uid="initial-test"), load_url=original,
            quote=lambda value: value, webview=MagicMock(), url=None,
        )
        self.addCleanup(lambda: __import__("app.macos", fromlist=["_MACOS_LOADERS"])._MACOS_LOADERS.pop("initial-test", None))

        self.assertTrue(_install_versioned_url_loader(browser, self._config(), foundation, app_helper))
        browser.load_url("https://portal.example.test/login")
        request.setValue_forHTTPHeaderField_.assert_called_once_with("1.0.1", "X-Wrapper-Version")
        browser.webview.loadRequest_.assert_called_once_with(request)
        self.assertEqual(browser.url, "https://portal.example.test/login")

    def test_loader_does_not_header_disallowed_destination_and_installs_once(self) -> None:
        foundation = SimpleNamespace(NSURL=MagicMock(), NSMutableURLRequest=MagicMock())
        browser = SimpleNamespace(
            pywebview_window=SimpleNamespace(uid="blocked-test"), load_url=MagicMock(),
            quote=lambda value: value, webview=MagicMock(), url=None,
        )
        original = browser.load_url
        helper = SimpleNamespace(callAfter=lambda callback: callback())
        self.addCleanup(lambda: __import__("app.macos", fromlist=["_MACOS_LOADERS"])._MACOS_LOADERS.pop("blocked-test", None))
        _install_versioned_url_loader(browser, self._config(), foundation, helper)
        installed = browser.load_url
        _install_versioned_url_loader(browser, self._config(), foundation, helper)
        self.assertIs(browser.load_url, installed)
        browser.load_url("https://evil.example.test/")
        original.assert_called_once_with("https://evil.example.test/")
        foundation.NSMutableURLRequest.requestWithURL_.assert_not_called()

    def test_navigation_decision_handler_runs_once(self) -> None:
        policies = []
        handler = _DecisionHandlerOnce(policies.append)

        handler(1)
        handler(0)

        self.assertEqual(policies, [1])
        self.assertTrue(handler.called)


if __name__ == "__main__":
    unittest.main()
