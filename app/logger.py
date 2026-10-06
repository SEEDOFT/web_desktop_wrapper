"""Centralized logging configuration for the application.

This module provides a configured logger instance for structured logging
across the application. It automatically detects production mode and adjusts
log levels accordingly.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.runtime_mode import is_packaged


class SanitizedFormatter(logging.Formatter):
    """Redact URL details and common credential fields, including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        message = re.sub(r"https?://[^\s<>]+", "[url]", message)
        message = re.sub(r"(?i)\bauthorization\s*[:=]\s*(?:Bearer|Basic)\s+[^\s,;]+", "authorization=[redacted]", message)
        return re.sub(
            r"(?i)[\"']?\b(password|token|secret|authorization|cookie|api[_-]?key)[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            r"\1=[redacted]", message,
        )


def _get_log_level() -> int:
    """Determine the appropriate log level based on production mode and environment."""
    log_level_env = os.getenv("LOG_LEVEL", "").upper()
    if log_level_env in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return getattr(logging, log_level_env)

    # In packaged/frozen apps, default to WARNING to reduce console noise
    if is_packaged():
        return logging.WARNING
    return logging.DEBUG


def _configure_root_logger() -> None:
    """Configure the root logger with appropriate handlers and formatting."""
    log_level = _get_log_level()

    formatter = SanitizedFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(console_handler)


def configure_release_logging(directory: Path) -> None:
    """Add bounded, sanitized release logs without changing console verbosity."""
    root = logging.getLogger()
    if any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        return
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "wrapper.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(SanitizedFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        root.setLevel(min(root.level, logging.INFO))
        root.addHandler(handler)
    except OSError:
        root.warning("Unable to create release diagnostic log")


# Initialize logging on module import
_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    return logging.getLogger(name)
