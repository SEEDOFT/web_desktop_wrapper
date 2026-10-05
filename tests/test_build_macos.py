from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.build_macos import (
    architecture_suffix,
    load_build_environment,
    notarize,
    parse_args,
    sha256_file,
    sign_direct_bundle,
    validate_direct_distribution,
    write_checksum,
)


class BuildMacOSTests(unittest.TestCase):
    def test_embeds_complete_environment_without_sidecar(self) -> None:
        import tools.build_macos as module

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            output = Path(directory) / "embedded_config.py"
            content = '# configuration\nAPP_WRAPPER_VERSION=1.0.1\nCUSTOM_SETTING="hello"\n'
            env_path.write_text(content, encoding="utf-8")
            with patch.object(module, "ENV_PATH", env_path), patch.object(module, "EMBEDDED_CONFIG_PATH", output):
                module.write_embedded_config({"wrapper_version": "1.0.1"})
            namespace: dict = {}
            exec(compile(output.read_text(encoding="utf-8"), str(output), "exec"), namespace)
            self.assertEqual(namespace["ENV_TEXT"], content)
            self.assertEqual(namespace["CONFIG"]["wrapper_version"], "1.0.1")

    def test_parse_args_defaults(self) -> None:
        with patch.dict("os.environ", {"BUILDER_ENGINE": "pyinstaller", "APP_WRAPPER_VERSION": "1.0.0"}, clear=False), patch("sys.argv", ["build_macos.py"]):
            args = parse_args()
        self.assertFalse(args.skip_dmg)
        self.assertEqual(args.builder, "pyinstaller")
        self.assertFalse(args.debug)
        self.assertFalse(args.onedir)
        self.assertEqual(args.wrapper_version, "1.0.0")
        self.assertEqual(args.allowed_host, [])
        self.assertEqual(args.distribution, "development")

    def test_load_build_environment_supplies_parser_defaults(self) -> None:
        import tools.build_macos as module

        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "BUILDER_ENGINE=nuitka\nAPP_WRAPPER_VERSION=3.2.1\n",
                encoding="utf-8",
            )
            with patch.object(module, "ENV_PATH", env_path), patch.dict(
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

    def test_validate_environment_rejects_non_macos(self) -> None:
        import tools.build_macos as module

        with patch.object(module.platform, "system", return_value="Windows"), self.assertRaisesRegex(SystemExit, "must be built on macOS"):
            module.validate_environment("pyinstaller")

    def test_validate_environment_reports_missing_modules(self) -> None:
        import tools.build_macos as module

        with (
            patch.object(module.platform, "system", return_value="Darwin"),
            patch.object(module.shutil, "which", return_value="/usr/bin/tool"),
            patch.object(module.importlib.util, "find_spec", side_effect=lambda name: None if name == "WebKit" else MagicMock()),
            self.assertRaisesRegex(SystemExit, "WebKit"),
        ):
            module.validate_environment("pyinstaller")

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
                "--distribution",
                "direct",
                "--signing-identity",
                "Developer ID Application: Example Corp (TEAMID1234)",
                "--notary-profile",
                "digi-notary",
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
            self.assertEqual(args.distribution, "direct")
            self.assertEqual(args.notary_profile, "digi-notary")

    def test_direct_distribution_requires_credentials(self) -> None:
        args = MagicMock(
            distribution="direct",
            skip_dmg=False,
            signing_identity="",
            notary_profile="",
        )
        with self.assertRaisesRegex(SystemExit, "signing-identity"):
            validate_direct_distribution(args)

    def test_direct_distribution_rejects_non_developer_id_identity(self) -> None:
        args = MagicMock(
            distribution="direct",
            skip_dmg=False,
            signing_identity="Apple Development: Example",
            notary_profile="digi-notary",
        )
        with self.assertRaisesRegex(SystemExit, "Developer ID Application"):
            validate_direct_distribution(args)

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
    def test_direct_signing_signs_nested_code_before_app(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codesign"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app_path = Path(temp_dir) / "Test.app"
            app_path.mkdir()
            nested = app_path / "Contents" / "Frameworks" / "sample.dylib"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"binary")
            identity = "Developer ID Application: Example Corp (TEAMID1234)"
            with patch("tools.build_macos.os.access", return_value=False):
                sign_direct_bundle(app_path, identity)

            calls = [call.args[0] for call in mock_run.call_args_list]
            codesign_calls = [call for call in calls if call[0] == "codesign"]
            self.assertIn(str(nested), codesign_calls[0])
            self.assertIn(str(app_path), codesign_calls[1])
            self.assertEqual(codesign_calls[2][:3], ["codesign", "--verify", "--deep"])

    @patch("tools.build_macos.run")
    def test_notarization_rejection_is_fatal_and_logged(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["xcrun"],
            returncode=0,
            stdout='{"id":"submission-1","status":"Invalid"}',
            stderr="",
        )
        import tools.build_macos as module

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "Test.dmg"
            artifact.write_bytes(b"dmg")
            with patch.object(module, "OUTPUT_ROOT", Path(temp_dir)):
                with self.assertRaisesRegex(SystemExit, "submission-1"):
                    notarize(artifact, "profile", "notarization.json")
                self.assertTrue((Path(temp_dir) / "notarization.json").is_file())


if __name__ == "__main__":
    unittest.main()
