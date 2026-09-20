"""Piece A: Data Loader — find and parse production data files from a directory."""
from __future__ import annotations

from pathlib import Path

from .parsers import parse_event_file, parse_oee_file, DowntimeEvent, OEEInterval


SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}


def load_data(data_dir: str | Path) -> tuple[list[DowntimeEvent], list[OEEInterval]]:
    """Load all supported files from a directory, auto-detecting event vs OEE files."""
    data_path = Path(data_dir)
    if not data_path.is_dir():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    events: list[DowntimeEvent] = []
    oee: list[OEEInterval] = []

    for f in sorted(data_path.iterdir()):
        if f.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        name = f.name.lower()
        if name.startswith("~") or name.startswith("."):
            continue
        if f.suffix.lower() in {".csv", ".tsv"}:
            try:
                from .web_loader import load_uploaded_file
                with f.open("rb") as handle:
                    parsed_events, parsed_oee, _ = load_uploaded_file(handle, f.name)
                events.extend(parsed_events)
                oee.extend(parsed_oee)
            except Exception:
                pass
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
        raise ValueError(f"No parseable production data files found in {data_dir}")

    return events, oee