from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.logger import SanitizedFormatter, _get_log_level, configure_release_logging


class ReleaseLoggingTests(unittest.TestCase):
    def test_packaged_logging_recognizes_nuitka_marker(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch("app.runtime_mode.sys.__nuitka_version__", "test", create=True):
            self.assertEqual(_get_log_level(), logging.WARNING)

    def test_credentials_and_url_parameters_are_removed(self) -> None:
        record = logging.LogRecord("test", logging.ERROR, "", 0,
            "Failed https://user:password@host.test/?token=private password=private token='other private' Authorization: Bearer private", (), None)
        formatted = SanitizedFormatter().format(record)
        self.assertNotIn("private", formatted)
        self.assertNotIn("host.test", formatted)
        self.assertIn("[redacted]", formatted)

    def test_json_credentials_and_exception_tracebacks_are_redacted(self) -> None:
        try:
            raise ValueError('{"password":"private","api_key":"private"}')
        except ValueError:
            import sys

            record = logging.LogRecord("test", logging.ERROR, "", 0, "Request failed", (), sys.exc_info())
            self.assertNotIn("private", SanitizedFormatter().format(record))

    def test_release_logs_rotate_and_setup_is_idempotent(self) -> None:
        root = logging.getLogger()
        original_level = root.level
        with tempfile.TemporaryDirectory() as directory:
            before = set(root.handlers)
            try:
                configure_release_logging(Path(directory))
                configure_release_logging(Path(directory))
                added = [handler for handler in root.handlers if handler not in before]
                self.assertEqual(len(added), 1)
                handler = added[0]
                handler.handle(logging.LogRecord("test", logging.INFO, "", 0, "version 1.0.1 token=private", (), None))
                handler.flush()
                self.assertNotIn("private", (Path(directory) / "wrapper.log").read_text(encoding="utf-8"))
                handler.doRollover()  # type: ignore[attr-defined]
                self.assertTrue((Path(directory) / "wrapper.log.1").is_file())
            finally:
                for handler in list(root.handlers):
                    if handler not in before:
                        root.removeHandler(handler)
                        handler.close()
                root.setLevel(original_level)
