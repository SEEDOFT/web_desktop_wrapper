from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.build_macos import (
    parse_args,
    remove_quarantine,
    sha256_file,
    sign_bundle,
    write_checksum,
)


class BuildMacOSTests(unittest.TestCase):
    def test_parse_args_defaults(self) -> None:
        with patch("sys.argv", ["build_macos.py"]):
            args = parse_args()
            self.assertFalse(args.skip_dmg)

    def test_parse_args_skip_dmg(self) -> None:
        with patch("sys.argv", ["build_macos.py", "--skip-dmg"]):
            args = parse_args()
            self.assertTrue(args.skip_dmg)

    def test_sha256_file_and_checksum_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_artifact.bin"
            test_file.write_bytes(b"hello universal macos build")

            digest = sha256_file(test_file)
            self.assertIsInstance(digest, str)
            self.assertEqual(len(digest), 64)

            write_checksum(test_file)
            checksum_path = test_file.with_suffix(test_file.suffix + ".sha256")
            self.assertTrue(checksum_path.is_file())
            content = checksum_path.read_text(encoding="utf-8")
            self.assertIn(digest, content)
            self.assertIn("test_artifact.bin", content)

    @patch("tools.build_macos.run")
    def test_remove_quarantine_directory(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["xattr"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir) / "Test.app"
            app_dir.mkdir()

            remove_quarantine(app_dir)

            self.assertEqual(mock_run.call_count, 2)
            mock_run.assert_any_call(
                ["xattr", "-r", "-d", "com.apple.quarantine", str(app_dir)],
                check=False,
            )
            mock_run.assert_any_call(
                ["xattr", "-c", "-r", str(app_dir)],
                check=False,
            )

    @patch("tools.build_macos.run")
    def test_remove_quarantine_single_file(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["xattr"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "Test.dmg"
            file_path.write_text("dummy")

            remove_quarantine(file_path)

            self.assertEqual(mock_run.call_count, 2)
            mock_run.assert_any_call(
                ["xattr", "-d", "com.apple.quarantine", str(file_path)],
                check=False,
            )
            mock_run.assert_any_call(
                ["xattr", "-c", str(file_path)],
                check=False,
            )

    @patch("tools.build_macos.run")
    def test_sign_bundle_clears_quarantine_before_and_after(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codesign"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app_path = Path(temp_dir) / "Test.app"
            app_path.mkdir()

            with patch("tools.build_macos.remove_quarantine") as mock_quarantine:
                sign_bundle(app_path)
                self.assertEqual(mock_quarantine.call_count, 2)
                mock_run.assert_called_once_with(
                    ["codesign", "--force", "--deep", "--sign", "-", "--options", "runtime", str(app_path)]
                )


if __name__ == "__main__":
    unittest.main()
