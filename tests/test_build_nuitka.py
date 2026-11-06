from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from tools.build import (
    _sync_tree,
    _write_if_changed,
    construct_nuitka_command,
    persistent_staged_application,
)


class BuildNuitkaTests(unittest.TestCase):
    def test_construct_nuitka_command_fast_mode(self) -> None:
        source_root = Path("/dummy/src")
        output_dir = Path("/dummy/out")
        report_path = Path("/dummy/report.xml")
        cmd = construct_nuitka_command(
            source_root=source_root,
            executable_name="TestApp",
            output_dir=output_dir,
            report_file=report_path,
            native_config=Path("/dummy/native.yml"),
            icon_path=None,
            is_onedir=True,
            fast_mode=True,
            debug_mode=False,
            platform="win32",
        )

        self.assertIn("--lto=no", cmd)
        self.assertNotIn("--onefile", cmd)
        self.assertNotIn("--remove-output", cmd)
        self.assertIn("--noinclude-default-mode=nofollow", cmd)
        self.assertIn("--include-module=webview", cmd)
        self.assertIn("--include-module=webview.platforms.edgechromium", cmd)
        self.assertIn("--nofollow-import-to=webview.platforms.gtk", cmd)
        self.assertIn("--nofollow-import-to=webview.platforms.qt", cmd)
        self.assertIn(f"--report={report_path}", cmd)
        self.assertEqual(cmd[-1], str(source_root / "run.py"))

    def test_construct_nuitka_command_release_mode(self) -> None:
        source_root = Path("/dummy/src")
        output_dir = Path("/dummy/out")
        cmd = construct_nuitka_command(
            source_root=source_root,
            executable_name="TestApp",
            output_dir=output_dir,
            report_file=None,
            native_config=None,
            icon_path=Path("/dummy/icon.ico"),
            is_onedir=False,
            fast_mode=False,
            debug_mode=True,
            platform="win32",
        )

        self.assertIn("--lto=yes", cmd)
        self.assertIn("--onefile", cmd)
        self.assertNotIn("--remove-output", cmd)
        self.assertIn("--windows-console-mode=force", cmd)
        self.assertIn(f"--windows-icon-from-ico={Path('/dummy/icon.ico').resolve()}", cmd)

    def test_sync_tree_and_persistent_staging_preserves_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            proj_root = temp_path / "proj"
            proj_app = proj_root / "app"
            proj_app.mkdir(parents=True)
            (proj_app / "main.py").write_text("print('hello')", encoding="utf-8")
            (proj_app / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")
            (proj_root / "run.py").write_text("import app", encoding="utf-8")
            (proj_root / ".env").write_text("APP_NAME=TestApp", encoding="utf-8")

            stage_root = temp_path / "stage"

            # Initial staging
            source_root = persistent_staged_application(proj_root, {"wrapper_version": "1.0.0"}, stage_root)
            staged_main = source_root / "app" / "main.py"
            staged_utils = source_root / "app" / "utils.py"
            self.assertTrue(staged_main.is_file())
            self.assertTrue(staged_utils.is_file())

            initial_utils_mtime = staged_utils.stat().st_mtime_ns

            # Sleep slightly to ensure timestamp would change if modified
            time.sleep(0.05)

            # Modify only main.py in project
            (proj_app / "main.py").write_text("print('updated')", encoding="utf-8")

            # Second staging
            persistent_staged_application(proj_root, {"wrapper_version": "1.0.0"}, stage_root)

            # utils.py was untouched; its mtime must be strictly preserved
            self.assertEqual(staged_utils.stat().st_mtime_ns, initial_utils_mtime)
            # main.py was modified; its content is updated
            self.assertEqual(staged_main.read_text(encoding="utf-8"), "print('updated')")

            # Delete utils.py in project
            (proj_app / "utils.py").unlink()
            persistent_staged_application(proj_root, {"wrapper_version": "1.0.0"}, stage_root)
            self.assertFalse(staged_utils.exists())


if __name__ == "__main__":
    unittest.main()
