from __future__ import annotations

import ctypes
import unittest
from unittest.mock import MagicMock, patch

from app.single_instance import (
    SingleInstanceLock,
    acquire_single_instance,
    activate_existing_window,
)


class SingleInstanceTests(unittest.TestCase):
    def test_single_instance_lock_release(self) -> None:
        mock_handle = MagicMock()
        lock = SingleInstanceLock(handle=mock_handle, is_windows=False)
        lock.release()
        self.assertIsNone(lock._handle)

    @unittest.skipUnless(hasattr(ctypes, "windll"), "Windows-only ctypes API")
    @patch("sys.platform", "win32")
    def test_windows_activate_existing_window(self) -> None:
        with (
            patch("ctypes.windll.user32.FindWindowW", return_value=12345) as mock_find,
            patch("ctypes.windll.user32.ShowWindow") as mock_show,
            patch("ctypes.windll.user32.SetForegroundWindow") as mock_fg,
        ):
            activate_existing_window("Test App")
            mock_find.assert_called_once_with(None, "Test App")
            mock_show.assert_called_once_with(12345, 9)
            mock_fg.assert_called_once_with(12345)

    def test_acquire_single_instance_success(self) -> None:
        lock = acquire_single_instance("test_app_unique_id_123", "Test App")
        if lock is not None:
            self.assertIsInstance(lock, SingleInstanceLock)
            lock.release()


if __name__ == "__main__":
    unittest.main()
