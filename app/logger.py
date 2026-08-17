"""Centralized logging configuration for the application.

This module provides a configured logger instance for structured logging
across the application. It automatically detects production mode and adjusts
log levels accordingly.
"""

from __future__ import annotations

import logging
import os
import sys


def _get_log_level() -> int:
    """Determine the appropriate log level based on production mode and environment."""
    log_level_env = os.getenv("LOG_LEVEL", "").upper()
    if log_level_env in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return getattr(logging, log_level_env)

    # In packaged/frozen apps, default to WARNING to reduce console noise
    if getattr(sys, "frozen", False):
        return logging.WARNING
    return logging.DEBUG


def _configure_root_logger() -> None:
    """Configure the root logger with appropriate handlers and formatting."""
    log_level = _get_log_level()

    formatter = logging.Formatter(
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


# Initialize logging on module import
_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    return logging.getLogger(name)
