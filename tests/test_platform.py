from __future__ import annotations

import unittest
from pathlib import Path

from app.platform import (
    browser_backend,
    persistent_storage_path,
    renderer_name,
    runtime_check_required,
)


class PlatformTests(unittest.TestCase):
    def test_selects_native_browser_backend(self) -> None:
        self.assertEqual(browser_backend("win32"), "edgechromium")
        self.assertEqual(browser_backend("darwin"), "cocoa")
        self.assertEqual(renderer_name("win32"), "edgechromium")
        self.assertEqual(renderer_name("darwin"), "wkwebview")

    def test_rejects_unsupported_platform(self) -> None:
        with self.assertRaises(RuntimeError):
            browser_backend("linux")

    def test_webview2_check_is_windows_only(self) -> None:
        self.assertTrue(runtime_check_required("win32"))
        self.assertFalse(runtime_check_required("darwin"))

    def test_macos_storage_uses_application_support(self) -> None:
        path = persistent_storage_path(
            "DIGI EXPRESS",
            "DIGI-EXPRESS-DIGI-Express-Admin",
            "darwin",
            Path("/Users/tester"),
        )
        self.assertEqual(
            path,
            Path("/Users/tester/Library/Application Support/DIGI EXPRESS/")
            / "DIGI-EXPRESS-DIGI-Express-Admin/WebKit",
        )

    def test_windows_storage_fallback_uses_local_app_data(self) -> None:
        path = persistent_storage_path(
            "DIGI EXPRESS",
            "profile",
            "win32",
            Path("C:/Users/tester"),
        )
        self.assertEqual(
            path,
            Path("C:/Users/tester/AppData/Local/DIGI EXPRESS/profile/WebView2"),
        )


if __name__ == "__main__":
    unittest.main()
