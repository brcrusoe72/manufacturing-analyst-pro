"""Piece A: Data Loader — find and parse Excel files from a directory."""
from __future__ import annotations

from pathlib import Path

from .parsers import parse_event_file, parse_oee_file, DowntimeEvent, OEEInterval


def load_data(data_dir: str | Path) -> tuple[list[DowntimeEvent], list[OEEInterval]]:
    """Load all Excel files from a directory, auto-detecting event vs OEE files."""
    data_path = Path(data_dir)
    if not data_path.is_dir():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    events: list[DowntimeEvent] = []
    oee: list[OEEInterval] = []

    for f in sorted(data_path.glob("*.xlsx")):
        name = f.name.lower()
        if name.startswith("~") or name.startswith("."):
            continue
        if "event" in name:
            events.extend(parse_event_file(f))
        elif "oee" in name:
            oee.extend(parse_oee_file(f))
        else:
            # Try both — event parser first, fall back to OEE
            try:
                parsed = parse_event_file(f)
                if parsed:
                    events.extend(parsed)
                    continue
            except Exception:
                pass
            try:
                parsed_oee = parse_oee_file(f)
                if parsed_oee:
                    oee.extend(parsed_oee)
            except Exception:
                pass

    if not events and not oee:
        raise ValueError(f"No parseable Excel files found in {data_dir}")

    return events, oee
