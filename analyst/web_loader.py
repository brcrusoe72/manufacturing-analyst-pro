"""Web-friendly data loader — works with uploaded file objects (BytesIO)."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from .parsers import parse_event_file, parse_oee_file, DowntimeEvent, OEEInterval
from .parsers.generic_parser import detect_and_parse, parse_generic_events, parse_generic_oee, _is_oee_file, _read_dataframe


def _is_traksys_event(headers: list[str]) -> bool:
    """Check if headers match Traksys Event Overview format."""
    normalized = [h.lower().strip() for h in headers]
    traksys_signals = {"eventid", "startdatetimeoffset", "enddatetimeoffset",
                       "durationseconds", "systemname", "eventcategoryname"}
    matches = sum(1 for h in normalized if any(t in h.replace(" ", "").lower() for t in traksys_signals))
    return matches >= 3


def _is_traksys_oee(headers: list[str]) -> bool:
    """Check if headers match Traksys OEE Overview format."""
    normalized = [h.lower().strip().replace(" ", "") for h in headers]
    traksys_signals = {"groupvalue", "availabilitydecimal", "performancedecimal",
                       "qualitydecimal", "oeedecimal", "intervalseconds"}
    matches = sum(1 for h in normalized if any(t in h for t in traksys_signals))
    return matches >= 3


def load_uploaded_file(
    file_obj: Any,
    filename: str,
) -> tuple[list[DowntimeEvent], list[OEEInterval], str]:
    """Load an uploaded file, auto-detecting format.

    Returns (events, oee_intervals, format_description).
    """
    # Save to temp for Traksys parsers (they need file paths)
    import tempfile
    import os

    suffix = Path(filename).suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if hasattr(file_obj, 'read'):
            data = file_obj.read()
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
        else:
            data = file_obj
        tmp.write(data)
        tmp.flush()
        tmp_path = tmp.name
        tmp.close()

        # Try to read headers for format detection
        try:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            headers, rows = _read_dataframe(
                io.BytesIO(data) if isinstance(data, bytes) else file_obj,
                filename,
            )
        except Exception:
            headers, rows = [], []

        # Try Traksys Event format first
        if headers and _is_traksys_event(headers):
            try:
                events = parse_event_file(tmp_path)
                if events:
                    return events, [], f"Traksys Event Overview ({len(events):,} events)"
            except Exception:
                pass

        # Try Traksys OEE format
        if headers and _is_traksys_oee(headers):
            try:
                oee = parse_oee_file(tmp_path)
                if oee:
                    return [], oee, f"Traksys OEE Overview ({len(oee):,} intervals)"
            except Exception:
                pass

        # Try generic parser
        try:
            buf = io.BytesIO(data) if isinstance(data, bytes) else file_obj
            if hasattr(buf, 'seek'):
                buf.seek(0)
            if headers and _is_oee_file(headers):
                oee = parse_generic_oee(buf, filename)
                if oee:
                    return [], oee, f"OEE data ({len(oee):,} intervals)"
            else:
                events = parse_generic_events(buf, filename)
                if events:
                    return events, [], f"Downtime events ({len(events):,} events)"
        except Exception as e:
            raise ValueError(
                f"Could not parse {filename}. Error: {str(e)}\n\n"
                f"Detected columns: {headers[:10] if headers else 'none'}\n\n"
                f"Expected columns like: date/timestamp, equipment/machine/reason, "
                f"duration (optional), line (optional)"
            ) from e

        raise ValueError(
            f"No parseable data found in {filename}. "
            f"Detected columns: {headers[:10] if headers else 'none'}"
        )

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def load_multiple_files(
    files: list[tuple[Any, str]],
) -> tuple[list[DowntimeEvent], list[OEEInterval], list[str]]:
    """Load multiple uploaded files, combining results.

    Args:
        files: list of (file_object, filename) tuples

    Returns:
        (all_events, all_oee, format_descriptions)
    """
    all_events: list[DowntimeEvent] = []
    all_oee: list[OEEInterval] = []
    descriptions: list[str] = []

    for file_obj, filename in files:
        events, oee, desc = load_uploaded_file(file_obj, filename)
        all_events.extend(events)
        all_oee.extend(oee)
        descriptions.append(f"{filename}: {desc}")

    return all_events, all_oee, descriptions
