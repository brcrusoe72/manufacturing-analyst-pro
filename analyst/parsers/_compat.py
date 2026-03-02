"""Compatibility stubs replacing Vigil's internal modules."""
from __future__ import annotations
import logging
from typing import Any


class ParseError(Exception):
    """Raised when a data file cannot be parsed."""


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"analyst.{name}")


def safe_cell_value(value: Any, *, row: int = 0, col: int = 0) -> Any:
    """Return cell value as-is. Vigil's version did security filtering; we trust local files."""
    return value
