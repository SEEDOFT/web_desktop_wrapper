from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.build_macos import (
    architecture_suffix,
    load_build_environment,
    parse_args,
    remove_quarantine,
    sha256_file,
    sign_bundle,
    strip_source_quarantine,
    write_checksum,
)


class BuildMacOSTests(unittest.TestCase):
    def test_parse_args_defaults(self) -> None:
        with patch.dict("os.environ", {"BUILDER_ENGINE": "pyinstaller", "APP_WRAPPER_VERSION": "1.0.0"}, clear=False):
            with patch("sys.argv", ["build_macos.py"]):
                args = parse_args()
        self.assertFalse(args.skip_dmg)
        self.assertEqual(args.builder, "pyinstaller")
        self.assertFalse(args.debug)
        self.assertFalse(args.onedir)
        self.assertEqual(args.wrapper_version, "1.0.0")
        self.assertEqual(args.allowed_host, [])

    def test_load_build_environment_supplies_parser_defaults(self) -> None:
        import tools.build_macos as module

        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "BUILDER_ENGINE=nuitka\nAPP_WRAPPER_VERSION=3.2.1\n",
                encoding="utf-8",
            )
            with patch.object(module, "ENV_PATH", env_path):
                with patch.dict(
                    "os.environ",
                    {"BUILDER_ENGINE": "pyinstaller", "APP_WRAPPER_VERSION": "1.0.0"},
                    clear=False,
                ):
                    load_build_environment()
                    with patch("sys.argv", ["build_macos.py"]):
                        args = parse_args()

        self.assertEqual(args.builder, "nuitka")
        self.assertEqual(args.wrapper_version, "3.2.1")

    def test_parse_args_skip_dmg(self) -> None:
        with patch("sys.argv", ["build_macos.py", "--skip-dmg"]):
            args = parse_args()
            self.assertTrue(args.skip_dmg)

    def test_parse_args_skip_quarantine_strip(self) -> None:
        with patch("sys.argv", ["build_macos.py", "--skip-quarantine-strip"]):
            args = parse_args()
            self.assertTrue(args.skip_quarantine_strip)

    def test_validate_environment_rejects_non_macos(self) -> None:
        import tools.build_macos as module

        with patch.object(module.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(SystemExit, "must be built on macOS"):
                module.validate_environment("pyinstaller")

    def test_validate_environment_reports_missing_modules(self) -> None:
        import tools.build_macos as module

        with patch.object(module.platform, "system", return_value="Darwin"):
            with patch.object(module.shutil, "which", return_value="/usr/bin/tool"):
                with patch.object(
                    module.importlib.util,
                    "find_spec",
                    side_effect=lambda name: None if name == "WebKit" else MagicMock(),
                ):
                    with self.assertRaisesRegex(SystemExit, "WebKit"):
                        module.validate_environment("pyinstaller")

    @patch("tools.build_macos.remove_quarantine")
    @patch("tools.build_macos.shutil.which", return_value=None)
    def test_strip_source_quarantine_covers_project_and_python(
        self,
        mock_which: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        import tools.build_macos as module
        with patch.object(module, "PROJECT_ROOT", Path("/project")):
            with patch.object(module.sys, "executable", "/usr/bin/python3"):
                with patch.object(Path, "exists", return_value=True):
                    strip_source_quarantine()
        calls = [call.args[0] for call in mock_remove.call_args_list]
        self.assertIn(Path("/project"), calls)
        self.assertIn(Path("/usr/bin/python3").resolve(), calls)
        self.assertIn(Path(sys.base_prefix).resolve(), calls)


    @patch("tools.build_macos.remove_quarantine")
    @patch("tools.build_macos.shutil.which", side_effect=lambda name: f"/usr/bin/{name}")
    def test_strip_source_quarantine_includes_tools(
        self,
        mock_which: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        with patch.object(Path, "exists", return_value=True):
            strip_source_quarantine()
        calls = [call.args[0] for call in mock_remove.call_args_list]
        for tool in ("lipo", "iconutil", "hdiutil", "ditto", "codesign", "xattr", "sips", "nuitka"):
            self.assertIn(Path(f"/usr/bin/{tool}").resolve(), calls)

    def test_parse_args_custom_flags(self) -> None:
        with patch(
            "sys.argv",
            [
                "build_macos.py",
                "--name",
                "DIGI Admin",
                "--builder",
                "nuitka",
                "--debug",
                "--onedir",
                "--allowed-host",
                "api.example.com",
                "--allow-subdomains",
                "--wrapper-version",
                "2.1.0",
                "--icon",
                "assets/digi_express.icns",
                "--windowed-size",
                "1440",
                "900",
            ],
        ):
            args = parse_args()
            self.assertEqual(args.name, "DIGI Admin")
            self.assertEqual(args.builder, "nuitka")
            self.assertTrue(args.debug)
            self.assertTrue(args.onedir)
            self.assertEqual(args.allowed_host, ["api.example.com"])
            self.assertTrue(args.allow_subdomains)
            self.assertEqual(args.wrapper_version, "2.1.0")
            self.assertEqual(args.icon, Path("assets/digi_express.icns"))
            self.assertEqual(args.windowed_size, [1440, 900])

    def test_architecture_suffix(self) -> None:
        self.assertEqual(architecture_suffix("pyinstaller"), "universal")
        self.assertEqual(architecture_suffix("nuitka"), "arm64") if __import__("platform").machine().lower() in {"arm64", "aarch64"} else self.assertNotEqual(architecture_suffix("nuitka"), "universal")

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
