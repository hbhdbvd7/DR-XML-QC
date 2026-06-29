"""Logging helpers for the local conform QC tool."""

from __future__ import annotations

import logging


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure process logging once."""
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
