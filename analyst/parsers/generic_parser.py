"""Generic CSV/Excel parser — auto-detect columns, handle messy real-world data."""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._compat import ParseError, get_logger
from ._parser_utils import _to_datetime, _to_float
from .event_parser import DowntimeEvent
from .oee_parser import OEEInterval, normalize_line_id

_log = get_logger("parsers.generic")

# Column name aliases for fuzzy matching
_TIMESTAMP_ALIASES = [
    "start", "start_time", "startdatetimeoffset", "datetime", "date_time",
    "timestamp", "time", "date", "begin", "start_date", "event_start",
    "occurred", "occurred_at", "created", "created_at",
]
_END_TIME_ALIASES = [
    "end", "end_time", "enddatetimeoffset", "stop", "stop_time",
    "end_date", "event_end", "finished", "completed",
]
_EQUIPMENT_ALIASES = [
    "equipment", "machine", "asset", "system", "device", "station",
    "eventcategoryname", "reason", "cause", "failure", "fault",
    "reason_code", "downtime_reason", "stop_reason", "category",
    "equipment_name", "machine_name", "asset_name",
]
_DURATION_ALIASES = [
    "duration", "duration_seconds", "durationseconds", "duration_min",
    "duration_minutes", "minutes", "seconds", "hours", "downtime",
    "downtime_minutes", "downtime_seconds", "downtime_hours",
    "elapsed", "elapsed_time", "total_time", "time_lost",
]
_LINE_ALIASES = [
    "line", "area", "cell", "zone", "department", "systemname",
    "line_id", "line_name", "production_line", "work_center",
    "workcenter", "cost_center",
]
_LOSS_TYPE_ALIASES = [
    "type", "loss_type", "category", "oee_type", "oeeeventtypename",
    "event_type", "stop_type", "downtime_type", "classification",
]
_NOTES_ALIASES = [
    "notes", "comments", "description", "details", "remarks", "note",
    "comment", "observation", "text",
]

# OEE-specific aliases
_OEE_ALIASES = ["oee", "oee_pct", "oee_decimal", "oeedecimal", "overall_equipment_effectiveness"]
_AVAILABILITY_ALIASES = ["availability", "availabilitydecimal", "avail", "avail_pct"]
_PERFORMANCE_ALIASES = ["performance", "performancedecimal", "perf", "perf_pct"]
_QUALITY_ALIASES = ["quality", "qualitydecimal", "qual", "qual_pct"]


def _normalize_header(h: str) -> str:
    """Lowercase, strip, replace spaces/special chars with underscore."""
    return re.sub(r'[^a-z0-9]', '', h.lower().strip())


def _match_column(headers: list[str], aliases: list[str]) -> int | None:
    """Find best matching column index for a set of aliases. Returns 0-based index or None."""
    normalized = [_normalize_header(h) for h in headers]
    # Exact match first
    for alias in aliases:
        norm_alias = _normalize_header(alias)
        for i, nh in enumerate(normalized):
            if nh == norm_alias:
                return i
    # Substring match
    for alias in aliases:
        norm_alias = _normalize_header(alias)
        for i, nh in enumerate(normalized):
            if norm_alias in nh or nh in norm_alias:
                if len(norm_alias) >= 3 and len(nh) >= 3:  # avoid false positives
                    return i
    return None


def _detect_duration_unit(header: str, sample_values: list[Any]) -> str:
    """Detect if duration is in seconds, minutes, or hours."""
    h = header.lower()
    if "second" in h or h.endswith("_s") or h == "durationseconds":
        return "seconds"
    if "hour" in h or h.endswith("_h"):
        return "hours"
    if "min" in h or h.endswith("_m"):
        return "minutes"
    # Guess from data: if median > 1000, probably seconds; if < 24, probably hours
    nums = [float(v) for v in sample_values if v is not None and v != "" and _to_float(v) is not None]
    if not nums:
        return "seconds"
    from statistics import median as _median
    med = _median(nums)
    if med > 500:
        return "seconds"
    if med < 24:
        return "hours"
    return "minutes"


def _to_seconds(value: Any, unit: str) -> float:
    """Convert a duration value to seconds."""
    f = _to_float(value)
    if f is None:
        return 0.0
    if unit == "minutes":
        return f * 60.0
    if unit == "hours":
        return f * 3600.0
    return f  # seconds


def _detect_date_format(sample_values: list[Any]) -> str | None:
    """Try to detect ambiguous date formats (MM/DD vs DD/MM)."""
    # Check if any value has day > 12 (unambiguously DD/MM or MM/DD)
    for v in sample_values:
        if v is None or isinstance(v, datetime):
            continue
        text = str(v).strip()
        m = re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', text)
        if m:
            first, second = int(m.group(1)), int(m.group(2))
            if first > 12:
                return "dmy"
            if second > 12:
                return "mdy"
    return "mdy"  # US default


def _parse_flexible_datetime(value: Any, date_format: str = "mdy") -> datetime | None:
    """Parse datetime from various formats."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    # ISO format
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass

    # Common formats
    formats = [
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%m-%d-%Y %H:%M:%S", "%m-%d-%Y",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d",
        "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M", "%m/%d/%y",
        "%d/%m/%y %H:%M:%S", "%d/%m/%y",
    ]
    if date_format == "dmy":
        # Prioritize DD/MM formats
        formats = [f for f in formats if "%d" in f[:3]] + [f for f in formats if "%d" not in f[:3]]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_oee_file(headers: list[str]) -> bool:
    """Check if this looks like an OEE file rather than a downtime/event file."""
    normalized = [_normalize_header(h) for h in headers]
    oee_signals = 0
    for nh in normalized:
        if any(_normalize_header(a) in nh for a in _OEE_ALIASES):
            oee_signals += 1
        if any(_normalize_header(a) in nh for a in _AVAILABILITY_ALIASES):
            oee_signals += 1
        if any(_normalize_header(a) in nh for a in _PERFORMANCE_ALIASES):
            oee_signals += 1
    return oee_signals >= 2


def _read_dataframe(file_obj: Any, filename: str = "") -> tuple[list[str], list[list[Any]]]:
    """Read headers and rows from CSV or Excel file object."""
    import pandas as pd

    name = filename.lower()
    if name.endswith(".csv") or name.endswith(".tsv"):
        # Try common separators
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        for sep in [',', '\t', ';', '|']:
            try:
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                df = pd.read_csv(file_obj, sep=sep, nrows=5)
                if len(df.columns) > 1:
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)
                    df = pd.read_csv(file_obj, sep=sep)
                    break
            except Exception:
                continue
        else:
            raise ParseError(f"Could not parse CSV file: {filename}")
    else:
        # Excel
        try:
            df = pd.read_excel(file_obj, engine='openpyxl')
        except Exception:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            df = pd.read_excel(file_obj)

    headers = [str(c) for c in df.columns.tolist()]
    rows = df.values.tolist()
    return headers, rows


def parse_generic_events(
    file_obj: Any,
    filename: str = "data.csv",
) -> list[DowntimeEvent]:
    """Parse a generic CSV/Excel file into DowntimeEvent records.

    Auto-detects column mappings by fuzzy header matching.
    Works with BytesIO, file paths, or file-like objects.
    """
    headers, rows = _read_dataframe(file_obj, filename)
    if not rows:
        return []

    # Map columns
    ts_col = _match_column(headers, _TIMESTAMP_ALIASES)
    end_col = _match_column(headers, _END_TIME_ALIASES)
    equip_col = _match_column(headers, _EQUIPMENT_ALIASES)
    dur_col = _match_column(headers, _DURATION_ALIASES)
    line_col = _match_column(headers, _LINE_ALIASES)
    loss_col = _match_column(headers, _LOSS_TYPE_ALIASES)
    notes_col = _match_column(headers, _NOTES_ALIASES)

    if ts_col is None and dur_col is None:
        raise ParseError(
            f"Cannot detect timestamp or duration columns in: {headers}. "
            f"Expected columns like: date, start_time, duration, equipment, machine, etc."
        )

    if equip_col is None:
        raise ParseError(
            f"Cannot detect equipment/machine column in: {headers}. "
            f"Expected columns like: equipment, machine, reason, cause, etc."
        )

    # Detect duration unit
    dur_unit = "seconds"
    if dur_col is not None:
        sample = [rows[i][dur_col] for i in range(min(50, len(rows)))]
        dur_unit = _detect_duration_unit(headers[dur_col], sample)

    # Detect date format
    date_format = "mdy"
    if ts_col is not None:
        sample_dates = [rows[i][ts_col] for i in range(min(20, len(rows)))]
        date_format = _detect_date_format(sample_dates)

    _log.info(
        "Generic parse: ts=%s end=%s equip=%s dur=%s(%s) line=%s loss=%s notes=%s date_fmt=%s",
        headers[ts_col] if ts_col is not None else None,
        headers[end_col] if end_col is not None else None,
        headers[equip_col] if equip_col is not None else None,
        headers[dur_col] if dur_col is not None else None,
        dur_unit,
        headers[line_col] if line_col is not None else None,
        headers[loss_col] if loss_col is not None else None,
        headers[notes_col] if notes_col is not None else None,
        date_format,
    )

    events: list[DowntimeEvent] = []
    bad_rows = 0

    for i, row in enumerate(rows):
        try:
            # Timestamp
            start = None
            if ts_col is not None:
                start = _parse_flexible_datetime(row[ts_col], date_format)
            if start is None and dur_col is not None:
                continue  # No timestamp, skip

            # End time
            end = None
            if end_col is not None:
                end = _parse_flexible_datetime(row[end_col], date_format)

            # Duration
            dur_sec = 0.0
            if dur_col is not None:
                dur_sec = _to_seconds(row[dur_col], dur_unit)
            elif start and end:
                dur_sec = (end - start).total_seconds()

            if dur_sec < 0:
                dur_sec = abs(dur_sec)

            # Compute end from start + duration if needed
            if start and not end and dur_sec > 0:
                from datetime import timedelta
                end = start + timedelta(seconds=dur_sec)
            elif start and not end:
                end = start

            if start is None:
                continue

            # Equipment
            equip_raw = str(row[equip_col]).strip() if row[equip_col] is not None else "Unknown"
            if not equip_raw or equip_raw.lower() in ("nan", "none", ""):
                equip_raw = "Unknown"

            # Line
            line_raw = ""
            if line_col is not None and row[line_col] is not None:
                line_raw = str(row[line_col]).strip()
            line_id = normalize_line_id(line_raw) if line_raw else "line-1"

            # Loss type
            loss_raw = ""
            if loss_col is not None and row[loss_col] is not None:
                loss_raw = str(row[loss_col]).strip().lower()

            # Notes
            notes = None
            if notes_col is not None and row[notes_col] is not None:
                n = str(row[notes_col]).strip()
                if n.lower() not in ("nan", "none", ""):
                    notes = n

            events.append(DowntimeEvent(
                event_id=i + 1,
                start_time=start,
                end_time=end,
                duration_seconds=dur_sec,
                line_id=line_id,
                line_raw_name=line_raw or line_id,
                equipment_id=None,  # generic files don't have normalized IDs
                equipment_raw_name=equip_raw,
                event_type="downtime",
                loss_type=loss_raw or "availability_loss",
                is_equipment_fault=True,
                notes=notes,
            ))
        except Exception:
            bad_rows += 1
            continue

    if len(rows) > 0 and bad_rows / len(rows) > 0.5:
        raise ParseError(f"Too many unparseable rows: {bad_rows}/{len(rows)}")

    events.sort(key=lambda e: e.start_time)
    _log.info("Generic parse: %d events from %s (%d bad rows)", len(events), filename, bad_rows)
    return events


def parse_generic_oee(
    file_obj: Any,
    filename: str = "data.csv",
) -> list[OEEInterval]:
    """Parse a generic OEE CSV/Excel file."""
    headers, rows = _read_dataframe(file_obj, filename)
    if not rows:
        return []

    ts_col = _match_column(headers, _TIMESTAMP_ALIASES)
    line_col = _match_column(headers, _LINE_ALIASES)
    oee_col = _match_column(headers, _OEE_ALIASES)
    avail_col = _match_column(headers, _AVAILABILITY_ALIASES)
    perf_col = _match_column(headers, _PERFORMANCE_ALIASES)
    qual_col = _match_column(headers, _QUALITY_ALIASES)

    if ts_col is None:
        raise ParseError(f"Cannot detect timestamp column for OEE data in: {headers}")
    if oee_col is None and avail_col is None:
        raise ParseError(f"Cannot detect OEE or Availability column in: {headers}")

    date_format = _detect_date_format([rows[i][ts_col] for i in range(min(20, len(rows)))])

    records: list[OEEInterval] = []
    for i, row in enumerate(rows):
        try:
            ts = _parse_flexible_datetime(row[ts_col], date_format)
            if ts is None:
                continue

            line_raw = ""
            if line_col is not None and row[line_col] is not None:
                line_raw = str(row[line_col]).strip()
            line_id = normalize_line_id(line_raw) if line_raw else "line-1"

            def _pct(col_idx: int | None) -> float | None:
                if col_idx is None:
                    return None
                v = _to_float(row[col_idx])
                if v is None:
                    return None
                # Auto-detect if percentage (0-100) or decimal (0-1)
                if v > 1.0:
                    return v / 100.0
                return v

            avail = _pct(avail_col)
            perf = _pct(perf_col)
            qual = _pct(qual_col)
            oee = _pct(oee_col)

            # Compute OEE if not provided
            if oee is None and avail is not None and perf is not None and qual is not None:
                oee = avail * perf * qual

            records.append(OEEInterval(
                timestamp=ts,
                line_id=line_id,
                line_raw_name=line_raw or line_id,
                availability=avail,
                performance=perf,
                quality=qual,
                oee=oee,
                mtbf_minutes=None,
                mttr_minutes=None,
                total_units=0,
                good_units=0,
                bad_units=0,
                downtime_seconds=0.0,
                interval_seconds=3600.0,
                cases_per_hour=0.0,
            ))
        except Exception:
            continue

    records.sort(key=lambda r: r.timestamp)
    _log.info("Generic OEE parse: %d records from %s", len(records), filename)
    return records


def detect_and_parse(
    file_obj: Any,
    filename: str = "data.csv",
) -> tuple[list[DowntimeEvent], list[OEEInterval]]:
    """Auto-detect file type and parse accordingly.

    Returns (events, oee_intervals). One list will typically be empty.
    """
    # Read headers to detect type
    headers, rows = _read_dataframe(file_obj, filename)
    if not headers or not rows:
        return [], []

    # Re-wrap data for parsing (since we already read it)
    import pandas as pd
    df = pd.DataFrame(rows, columns=headers)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    if _is_oee_file(headers):
        oee = parse_generic_oee(buf, filename)
        return [], oee
    else:
        events = parse_generic_events(buf, filename)
        return events, []
