from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build import staged_application


class BuildStagingTests(unittest.TestCase):
    def test_full_environment_is_isolated_and_cleaned_even_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            original = root / "app" / "embedded_config.py"
            original.write_text("CONFIG = {'local': True}\n", encoding="utf-8")
            (root / "run.py").write_text("import app\n", encoding="utf-8")
            environment = "APP_WRAPPER_VERSION=1.0.1\nCUSTOM_VALUE=complete\n"
            (root / ".env").write_text(environment, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "builder failure"), staged_application(root, {"wrapper_version": "2.0.0"}) as source:
                namespace: dict = {}
                exec(compile((source / "app" / "embedded_config.py").read_text(encoding="utf-8"), "embedded", "exec"), namespace)
                self.assertEqual(namespace["ENV_TEXT"], environment)
                self.assertEqual(namespace["CONFIG"]["wrapper_version"], "2.0.0")
                self.assertFalse((source / ".env").exists())
                self.assertEqual(original.read_text(encoding="utf-8"), "CONFIG = {'local': True}\n")
                raise RuntimeError("builder failure")
            self.assertFalse(source.exists())
            self.assertEqual(original.read_text(encoding="utf-8"), "CONFIG = {'local': True}\n")
