from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.browser import (
    _clear_http_cache,
    _open_find_dialog,
    _reload_after_cache_clear,
    _shortcut_action,
    _swipe_action_from_message,
)


class BrowserShortcutTests(unittest.TestCase):
    def test_refresh_shortcuts_are_recognized(self) -> None:
        self.assertEqual(_shortcut_action("r", ctrl=True), "reload")
        self.assertEqual(_shortcut_action("F5"), "reload")

    def test_hard_refresh_shortcut_is_recognized(self) -> None:
        self.assertEqual(_shortcut_action("F5", ctrl=True, shift=True), "hard_reload")
        self.assertEqual(_shortcut_action("r", ctrl=True, shift=True), "hard_reload")

    def test_clear_browsing_data_shortcut_is_explicit(self) -> None:
        self.assertEqual(
            _shortcut_action("delete", ctrl=True, shift=True),
            "clear_browsing_data",
        )
        self.assertEqual(
            _shortcut_action(46, ctrl=True, shift=True),
            "clear_browsing_data",
        )

    def test_hard_refresh_falls_back_to_safe_reload(self) -> None:
        core_webview = Mock()
        invoked_callbacks = []

        with patch("app.browser._clear_http_cache", return_value=None) as clear_cache:
            _reload_after_cache_clear(core_webview, invoked_callbacks.append)

        clear_cache.assert_called_once_with(core_webview.Profile)
        core_webview.Profile.ClearBrowsingDataAsync.assert_not_called()
        self.assertEqual(len(invoked_callbacks), 1)
        invoked_callbacks[0]()
        core_webview.Reload.assert_called_once_with()

    def test_hard_refresh_clears_only_http_cache(self) -> None:
        profile = Mock()
        kinds_type = object()
        cache_kind = object()
        clear_task = object()
        profile.GetType.return_value.Assembly.GetType.return_value = kinds_type
        profile.ClearBrowsingDataAsync.return_value = clear_task
        enum = Mock()
        enum.Parse.return_value = cache_kind

        with patch.dict(sys.modules, {"System": SimpleNamespace(Enum=enum)}):
            result = _clear_http_cache(profile)

        enum.Parse.assert_called_once_with(kinds_type, "DiskCache")
        profile.ClearBrowsingDataAsync.assert_called_once_with(cache_kind)
        self.assertIs(result, clear_task)

    def test_window_shortcuts_are_recognized(self) -> None:
        self.assertEqual(_shortcut_action("w", ctrl=True), "close")
        self.assertEqual(_shortcut_action(87, ctrl=True), "close")
        self.assertEqual(_shortcut_action("home", ctrl=True), "home")
        self.assertEqual(_shortcut_action(36, ctrl=True), "home")
        self.assertEqual(_shortcut_action("f11"), "fullscreen")
        self.assertEqual(_shortcut_action(122), "fullscreen")

    def test_numpad_zoom_keys_are_recognized(self) -> None:
        self.assertEqual(_shortcut_action(107, ctrl=True), "zoom_in")
        self.assertEqual(_shortcut_action(109, ctrl=True), "zoom_out")
        self.assertEqual(_shortcut_action(96, ctrl=True), "zoom_reset")

    def test_find_and_print_shortcuts_are_recognized(self) -> None:
        self.assertEqual(_shortcut_action("f", ctrl=True), "find")
        self.assertEqual(_shortcut_action(70, ctrl=True), "find")
        self.assertEqual(_shortcut_action("p", ctrl=True), "print")
        self.assertEqual(_shortcut_action(80, ctrl=True), "print")

    def test_find_dialog_prefers_open_find_dialog(self) -> None:
        core_webview = Mock()
        core_webview.OpenFindDialog = Mock()
        _open_find_dialog(core_webview)
        core_webview.OpenFindDialog.assert_called_once_with()

    def test_find_dialog_falls_back_to_find_api(self) -> None:
        core_webview = Mock()
        core_webview.OpenFindDialog = None
        core_webview.Find = Mock()
        core_webview.Environment.CreateFindOptions.return_value = Mock()
        _open_find_dialog(core_webview)
        options = core_webview.Environment.CreateFindOptions.return_value
        self.assertEqual(options.FindTerm, "")
        self.assertFalse(options.SuppressDefaultFindDialog)
        core_webview.Find.StartAsync.assert_called_once_with(options)

    def test_find_dialog_survives_missing_api(self) -> None:
        _open_find_dialog(Mock())

    def test_back_and_forward_shortcuts_are_recognized(self) -> None:
        self.assertEqual(_shortcut_action("left", alt=True), "back")
        self.assertEqual(_shortcut_action(37, alt=True), "back")
        self.assertEqual(_shortcut_action("right", alt=True), "forward")
        self.assertEqual(_shortcut_action(39, alt=True), "forward")
        self.assertIsNone(_shortcut_action("left", ctrl=True))
        self.assertIsNone(_shortcut_action("right"))

    def test_swipe_messages_map_to_navigation(self) -> None:
        self.assertEqual(
            _swipe_action_from_message(
                '{"type": "horizontalSwipe", "direction": "back"}'
            ),
            "back",
        )
        self.assertEqual(
            _swipe_action_from_message(
                '{"type": "horizontalSwipe", "direction": "forward"}'
            ),
            "forward",
        )

    def test_swipe_messages_ignore_unrelated_payloads(self) -> None:
        self.assertIsNone(_swipe_action_from_message(None))
        self.assertIsNone(_swipe_action_from_message("not json"))
        self.assertIsNone(_swipe_action_from_message("[]"))
        self.assertIsNone(
            _swipe_action_from_message('{"type": "other", "direction": "back"}')
        )
        self.assertIsNone(
            _swipe_action_from_message(
                '{"type": "horizontalSwipe", "direction": "up"}'
            )
        )

    def test_unknown_shortcuts_are_ignored(self) -> None:
        self.assertIsNone(_shortcut_action("x", ctrl=True))
        self.assertIsNone(_shortcut_action(99))
        self.assertIsNone(_shortcut_action(None))


if __name__ == "__main__":
    unittest.main()
