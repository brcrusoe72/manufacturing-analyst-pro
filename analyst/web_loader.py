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
    """Check if headers match Traksys OEE Overview flat format."""
    normalized = [h.lower().strip().replace(" ", "") for h in headers]
    traksys_signals = {"groupvalue", "availabilitydecimal", "performancedecimal",
                       "qualitydecimal", "oeedecimal", "intervalseconds"}
    matches = sum(1 for h in normalized if any(t in h for t in traksys_signals))
    return matches >= 3


def _is_traksys_pivot_oee(headers: list[str]) -> bool:
    """Check if headers match Traksys OEE pivot/crosstab format.

    This format has: GroupValue, SeriesLabel (or SeriesValue), Value
    but NOT the flat decimal columns like AvailabilityDecimal.
    """
    normalized = {h.lower().strip().replace(" ", "") for h in headers}
    has_group = "groupvalue" in normalized
    has_series = "serieslabel" in normalized or "seriesvalue" in normalized
    has_value = "value" in normalized
    has_flat = "availabilitydecimal" in normalized or "oeedecimal" in normalized
    return has_group and has_series and has_value and not has_flat


def _parse_traksys_pivot_oee(
    file_obj: Any,
    filename: str,
) -> list[OEEInterval]:
    """Parse Traksys pivot/crosstab OEE export into OEEInterval records.

    Expected columns: GroupValue (timestamp), SeriesLabel (metric name), Value (metric value).
    Optional: GroupLabel, SeriesValue, Start (line info).
    Pivots rows like:
        GroupValue=2025-12-01, SeriesLabel=Availability, Value=0.85
        GroupValue=2025-12-01, SeriesLabel=Performance, Value=0.92
    Into OEEInterval records with availability=0.85, performance=0.92, etc.
    """
    from .parsers.oee_parser import OEEInterval, normalize_line_id
    from .parsers._parser_utils import _to_datetime, _to_float

    headers, rows = _read_dataframe(file_obj, filename)
    if not rows:
        return []

    # Find column indices (case-insensitive)
    col_map = {}
    for i, h in enumerate(headers):
        col_map[h.lower().strip().replace(" ", "")] = i

    group_idx = col_map.get("groupvalue")
    series_label_idx = col_map.get("serieslabel")
    series_value_idx = col_map.get("seriesvalue")
    value_idx = col_map.get("value")
    # Try to get line info from Start column, GroupLabel, or filename
    start_idx = col_map.get("start")
    group_label_idx = col_map.get("grouplabel")

    if group_idx is None or value_idx is None:
        return []

    # Use SeriesLabel if available, else SeriesValue
    metric_idx = series_label_idx if series_label_idx is not None else series_value_idx
    if metric_idx is None:
        return []

    # Infer line from filename (e.g., "OEE Overview_L2_job.xlsx" -> line-2)
    from .parsers._parser_utils import _infer_line_id_from_filename
    fallback_line = _infer_line_id_from_filename(filename) or "line-unknown"

    # Group by timestamp -> {metric: value}
    from collections import defaultdict
    groups: dict[str, dict[str, float | None]] = defaultdict(dict)
    group_lines: dict[str, str] = {}

    # Metric name normalization
    _METRIC_MAP = {
        "availability": "availability",
        "avail": "availability",
        "performance": "performance",
        "perf": "performance",
        "quality": "quality",
        "qual": "quality",
        "oee": "oee",
        "overallequipmenteffectiveness": "oee",
        "mtbf": "mtbf",
        "mttr": "mttr",
    }

    for row in rows:
        ts_raw = row[group_idx] if group_idx < len(row) else None
        metric_raw = row[metric_idx] if metric_idx < len(row) else None
        val_raw = row[value_idx] if value_idx < len(row) else None

        if ts_raw is None or metric_raw is None:
            continue

        ts_key = str(ts_raw)
        metric_str = str(metric_raw).strip().lower().replace(" ", "")

        # Find line name from GroupLabel or Start column
        line_raw = ""
        if group_label_idx is not None and group_label_idx < len(row) and row[group_label_idx]:
            line_raw = str(row[group_label_idx]).strip()
        elif start_idx is not None and start_idx < len(row) and row[start_idx]:
            line_raw = str(row[start_idx]).strip()

        # Map to canonical metric name
        mapped = None
        for prefix, canonical in _METRIC_MAP.items():
            if metric_str.startswith(prefix):
                mapped = canonical
                break

        if mapped:
            val = _to_float(val_raw)
            groups[ts_key][mapped] = val

        if line_raw and ts_key not in group_lines:
            group_lines[ts_key] = line_raw

    # Convert grouped data to OEEInterval records
    records: list[OEEInterval] = []
    for ts_key, metrics in groups.items():
        ts = _to_datetime(ts_key)
        if ts is None:
            continue

        avail = metrics.get("availability")
        perf = metrics.get("performance")
        qual = metrics.get("quality")
        oee = metrics.get("oee")

        # Auto-detect percentage vs decimal
        def _norm_pct(v: float | None) -> float | None:
            if v is None:
                return None
            return v / 100.0 if v > 1.0 else v

        avail = _norm_pct(avail)
        perf = _norm_pct(perf)
        qual = _norm_pct(qual)
        oee = _norm_pct(oee)

        # Compute OEE if not provided
        if oee is None and avail is not None and perf is not None and qual is not None:
            oee = avail * perf * qual

        line_raw = group_lines.get(ts_key, "")
        line_id = normalize_line_id(line_raw) if line_raw else fallback_line

        mtbf = metrics.get("mtbf")
        mttr = metrics.get("mttr")

        records.append(OEEInterval(
            timestamp=ts,
            line_id=line_id,
            line_raw_name=line_raw or line_id,
            availability=avail,
            performance=perf,
            quality=qual,
            oee=oee,
            mtbf_minutes=mtbf,
            mttr_minutes=mttr,
            total_units=0,
            good_units=0,
            bad_units=0,
            downtime_seconds=0.0,
            interval_seconds=3600.0,
            cases_per_hour=0.0,
        ))

    records.sort(key=lambda r: r.timestamp)
    return records


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

        # Try Traksys pivot OEE format (GroupValue + SeriesLabel + Value)
        if headers and _is_traksys_pivot_oee(headers):
            try:
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                oee = _parse_traksys_pivot_oee(
                    io.BytesIO(data) if isinstance(data, bytes) else file_obj,
                    filename,
                )
                if oee:
                    return [], oee, f"Traksys OEE Pivot ({len(oee):,} intervals)"
            except Exception:
                pass

        # Try Traksys OEE flat format
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
