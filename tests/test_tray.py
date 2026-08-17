from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.config import AppConfig
from app.tray import cleanup_system_tray, setup_system_tray


class TrayTests(unittest.TestCase):
    def tearDown(self) -> None:
        cleanup_system_tray()

    def _config(self, enable_tray: bool = True, minimize_to_tray: bool = False) -> AppConfig:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "ENABLE_SYSTEM_TRAY": str(enable_tray).lower(),
                "MINIMIZE_TO_TRAY": str(minimize_to_tray).lower(),
            },
            clear=True,
        ):
            return AppConfig.load()

    def test_tray_cleanup_safe_when_empty(self) -> None:
        cleanup_system_tray()

    def test_setup_tray_disabled(self) -> None:
        config = self._config(enable_tray=False)
        result = setup_system_tray(MagicMock(), MagicMock(), config, lambda fn: fn())
        self.assertIsNone(result)

    @patch("sys.platform", "linux")
    def test_setup_tray_non_windows_safe(self) -> None:
        config = self._config(enable_tray=True)
        result = setup_system_tray(MagicMock(), MagicMock(), config, lambda fn: fn())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
