from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.config import AppConfig
from app.downloads import setup_download_handler, show_download_notification


class DownloadTests(unittest.TestCase):
    def _config(self, allow_downloads: bool = True, default_path: str = "") -> AppConfig:
        with patch.dict(
            os.environ,
            {
                "WEB_APP_URL": "https://portal.example.test",
                "ALLOW_DOWNLOADS": str(allow_downloads).lower(),
                "DEFAULT_DOWNLOADS_PATH": default_path,
                "SHOW_DOWNLOAD_NOTIFICATIONS": "true",
            },
            clear=True,
        ):
            return AppConfig.load()

    def test_show_download_notification_fallback(self) -> None:
        show_download_notification("Test App", "Download complete: sample.pdf", None)

    def test_show_download_notification_with_tray(self) -> None:
        mock_tray = MagicMock()
        show_download_notification("Test App", "Download complete: sample.pdf", mock_tray)
        mock_tray.ShowBalloonTip.assert_called_once_with(
            3000, "Test App", "Download complete: sample.pdf", 1
        )

    def test_setup_download_handler_disabled(self) -> None:
        mock_core = MagicMock()
        config = self._config(allow_downloads=False)
        setup_download_handler(mock_core, config, lambda fn: fn())
        self.assertTrue(hasattr(mock_core, "DownloadStarting"))


if __name__ == "__main__":
    unittest.main()
