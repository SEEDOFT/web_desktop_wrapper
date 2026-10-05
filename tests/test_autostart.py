from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch

from app.autostart import set_autostart_macos, set_autostart_windows, sync_autostart


class AutostartTests(unittest.TestCase):
    @patch("sys.platform", "linux")
    def test_sync_autostart_unsupported_platform(self) -> None:
        result = sync_autostart("Test App", "Test Org", True)
        self.assertFalse(result)

    @unittest.skipUnless(importlib.util.find_spec("winreg"), "Windows-only registry API")
    @patch("sys.platform", "win32")
    def test_set_autostart_windows_guard(self) -> None:
        # Should gracefully return boolean without raising unhandled exceptions
        with patch("winreg.OpenKey", side_effect=OSError("Access denied")):
            result = set_autostart_windows("Test App", "C:\\App.exe", True)
            self.assertFalse(result)

    @patch("sys.platform", "darwin")
    def test_set_autostart_macos_guard(self) -> None:
        with patch("pathlib.Path.mkdir", side_effect=OSError("Read-only")):
            result = set_autostart_macos("com.test.app", "/Applications/App.app", True)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
