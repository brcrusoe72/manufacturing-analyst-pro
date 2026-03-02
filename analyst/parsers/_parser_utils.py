"""Shared utilities for Traksys MES Excel parsers.

Contains common cell extraction, type conversion, and filename inference
functions used across event, OEE, and schedule parsers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _cell(row: tuple[Any, ...], one_based_idx: int) -> Any:
    """Return a row cell by 1-based index, or ``None`` if out of bounds."""
    if one_based_idx <= 0:
        return None
    zero = one_based_idx - 1
    return row[zero] if zero < len(row) else None


def _to_datetime(value: Any) -> datetime | None:
    """Convert a value to a timezone-aware UTC ``datetime`` when possible."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_text(value: Any) -> str:
    """Convert a cell value to a trimmed string, returning empty string for ``None``."""
    return "" if value is None else str(value).strip()


def _to_float(value: Any) -> float | None:
    """Convert a value to ``float`` or return ``None`` on blank/invalid input."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int:
    """Convert a value to ``int`` with ``0`` fallback for blank/invalid input."""
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _infer_line_id_from_filename(path: str | Path) -> str | None:
    """Infer ``line-N`` from common TrakSYS-style file names."""
    text = Path(path).name.strip().lower()
    match = re.search(r"(?:^|[_\s-])l(?:ine)?\s*[-_ ]*(\d+)(?:[_\s.-]|$)", text)
    if match:
        return f"line-{int(match.group(1))}"
    return None
