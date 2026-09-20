"""Shared parser utilities for cache I/O and timestamp normalization.

Extracted from event_parser.py and oee_parser.py to eliminate duplication.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ._compat import get_logger
from ._parser_utils import _to_datetime  # re-export for convenience
from ..security import parser_cache_enabled

_log = get_logger("connectors.parsers.utils")

normalize_timestamp = _to_datetime  # datetime | None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_DIR: Path | None = None


def get_cache_dir() -> Path:
    """Return (and lazily create) the shared parser cache directory."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(os.environ.get("MFG_AGENT_CACHE_DIR", "cache"))
        if parser_cache_enabled():
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def read_cache(path: Path, cache_version: int) -> dict[str, Any] | None:
    """Read a JSON cache file and return its payload if version + mtime match.

    Returns the full dict (including ``items``) on hit, or ``None`` on miss /
    corruption / version mismatch.  The caller must still supply ``source_mtime``
    externally — this function only reads what's on disk and checks
    ``cache_version``.
    """
    if not parser_cache_enabled() or not path.exists():
        return None
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        _log.debug("cache_load_failed path=%s err=%s", path, exc)
        return None
    if int(payload.get("cache_version", 0)) != cache_version:
        return None
    return payload


def write_cache(
    path: Path,
    data: list[dict[str, Any]],
    cache_version: int,
    source_mtime: float,
) -> None:
    """Write a JSON cache file with version and source-mtime envelope."""
    if not parser_cache_enabled():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "cache_version": cache_version,
            "source_mtime": source_mtime,
            "items": data,
        },
        indent=2,
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        tmp_name = handle.name
    os.replace(tmp_name, path)