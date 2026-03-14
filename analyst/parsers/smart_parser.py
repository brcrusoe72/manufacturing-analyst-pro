"""Smart Parser — AI-powered schema detection for any manufacturing data file.

Instead of hardcoding column names per MES vendor, this parser:
1. Reads headers + sample rows from the file
2. Asks a cheap LLM to classify columns (timestamp, equipment, duration, OEE metrics, etc.)
3. Uses the mapping to parse the full file into standard records

One parser for any format. Traksys, SAP, Ignition, manual Excel — doesn't matter.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from ._compat import ParseError, get_logger
from ._parser_utils import _to_datetime, _to_float, _to_int, _infer_line_id_from_filename
from .oee_parser import OEEInterval, normalize_line_id
from .event_parser import DowntimeEvent

_log = get_logger("parsers.smart")

# ── Schema Detection Prompt ──

_SCHEMA_PROMPT = """You are a manufacturing data expert. Given column headers and sample rows from a production data file, classify each column.

RESPOND WITH ONLY valid JSON — no markdown, no explanation.

Return this structure:
{
  "file_type": "events" | "oee" | "pivot_oee" | "unknown",
  "columns": {
    "<original_column_name>": "<role>"
  },
  "pivot_info": {
    "metric_column": "<column containing metric names like Availability, OEE>",
    "value_column": "<column containing the metric values>",
    "group_column": "<column containing timestamps/grouping>"
  } // only if file_type is "pivot_oee", otherwise omit
}

Column roles (use exactly these strings):
- "timestamp" — event start time or interval timestamp
- "end_time" — event end time
- "equipment" — machine/equipment name or failure reason/category
- "duration_seconds" — downtime duration in seconds
- "duration_minutes" — downtime duration in minutes  
- "duration_hours" — downtime duration in hours
- "line" — production line identifier
- "oee" — OEE value (0-1 decimal or 0-100 percent)
- "availability" — availability metric
- "performance" — performance metric
- "quality" — quality metric
- "mtbf" — mean time between failures (minutes)
- "mttr" — mean time to repair (minutes)
- "total_units" — total units produced
- "good_units" — good/accepted units
- "bad_units" — rejected/bad units
- "downtime_seconds" — total downtime in seconds for an interval
- "interval_seconds" — interval duration in seconds
- "loss_type" — type of loss (availability, performance, quality)
- "notes" — freetext notes/comments
- "metric_name" — in pivot tables, the column that says WHAT metric each row represents
- "metric_value" — in pivot tables, the column containing the metric's value
- "group_key" — grouping/timestamp key in pivot tables
- "group_label" — human label for the group
- "series_order" — display ordering (ignore)
- "ignore" — not useful for analysis

IMPORTANT:
- If the data has rows where each row is ONE metric for ONE timestamp (e.g., one row = "Availability" for "2025-12-01"), that's "pivot_oee"
- If each row has ALL metrics as separate columns (AvailabilityDecimal, PerformanceDecimal...), that's "oee"  
- If rows represent individual downtime/stop events with equipment + duration, that's "events"
- Column headers may be dates (like "2025-12-01 00:00:00") — classify those as "ignore" unless they're clearly timestamps for every row
- A column header that IS a date but contains line/area names in the rows → classify as "line"

Headers: {headers}

Sample rows (first 5):
{sample_rows}
"""


def _detect_schema(headers: list[str], sample_rows: list[list[Any]]) -> dict:
    """Use LLM to classify columns and detect file structure."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Format sample rows for the prompt
    sample_text = ""
    for i, row in enumerate(sample_rows[:5]):
        row_strs = [str(v)[:50] for v in row]  # truncate long values
        sample_text += f"  Row {i+1}: {row_strs}\n"

    prompt = _SCHEMA_PROMPT.format(
        headers=json.dumps(headers),
        sample_rows=sample_text,
    )

    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1000,
    )

    text = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        schema = json.loads(text)
    except json.JSONDecodeError as e:
        _log.warning("LLM returned invalid JSON: %s", text[:200])
        raise ParseError(f"Schema detection failed: invalid JSON from LLM") from e

    _log.info("Smart parser detected: type=%s columns=%s", schema.get("file_type"), schema.get("columns"))
    return schema


def _find_col(headers: list[str], schema: dict, role: str) -> int | None:
    """Find column index for a given role in the schema mapping."""
    col_map = schema.get("columns", {})
    for col_name, col_role in col_map.items():
        if col_role == role:
            try:
                return headers.index(col_name)
            except ValueError:
                # Try case-insensitive match
                for i, h in enumerate(headers):
                    if str(h).strip() == col_name.strip():
                        return i
    return None


def smart_parse(
    file_obj: Any,
    filename: str,
) -> tuple[list[DowntimeEvent], list[OEEInterval], str]:
    """Parse any manufacturing data file using AI schema detection.

    Returns (events, oee_intervals, description).
    """
    from .generic_parser import _read_dataframe

    headers, rows = _read_dataframe(file_obj, filename)
    if not headers or not rows:
        raise ParseError(f"No data in {filename}")

    # Detect schema
    schema = _detect_schema(headers, rows[:5])
    file_type = schema.get("file_type", "unknown")

    if file_type == "unknown":
        raise ParseError(
            f"Could not determine file type for {filename}. "
            f"Columns: {headers[:10]}"
        )

    fallback_line = _infer_line_id_from_filename(filename) or "line-1"

    if file_type == "events":
        events = _parse_events_from_schema(headers, rows, schema, filename, fallback_line)
        return events, [], f"Auto-detected events ({len(events):,} records)"

    elif file_type == "oee":
        oee = _parse_oee_from_schema(headers, rows, schema, filename, fallback_line)
        return [], oee, f"Auto-detected OEE ({len(oee):,} intervals)"

    elif file_type == "pivot_oee":
        oee = _parse_pivot_oee_from_schema(headers, rows, schema, filename, fallback_line)
        return [], oee, f"Auto-detected pivot OEE ({len(oee):,} intervals)"

    else:
        raise ParseError(f"Unsupported file type '{file_type}' for {filename}")


def _parse_events_from_schema(
    headers: list[str],
    rows: list[list[Any]],
    schema: dict,
    filename: str,
    fallback_line: str,
) -> list[DowntimeEvent]:
    """Parse event/downtime data using AI-detected schema."""
    ts_col = _find_col(headers, schema, "timestamp")
    end_col = _find_col(headers, schema, "end_time")
    equip_col = _find_col(headers, schema, "equipment")
    line_col = _find_col(headers, schema, "line")
    loss_col = _find_col(headers, schema, "loss_type")
    notes_col = _find_col(headers, schema, "notes")

    # Find duration column (any unit)
    dur_col = None
    dur_unit = "seconds"
    for role, unit in [("duration_seconds", "seconds"), ("duration_minutes", "minutes"), ("duration_hours", "hours")]:
        dur_col = _find_col(headers, schema, role)
        if dur_col is not None:
            dur_unit = unit
            break

    if ts_col is None:
        raise ParseError(f"No timestamp column detected in {filename}")
    if equip_col is None:
        raise ParseError(f"No equipment column detected in {filename}")

    events: list[DowntimeEvent] = []
    bad = 0

    for i, row in enumerate(rows):
        try:
            start = _to_datetime(row[ts_col]) if ts_col < len(row) else None
            if start is None:
                continue

            end = _to_datetime(row[end_col]) if end_col is not None and end_col < len(row) else None

            dur_sec = 0.0
            if dur_col is not None and dur_col < len(row):
                val = _to_float(row[dur_col]) or 0.0
                if dur_unit == "minutes":
                    dur_sec = val * 60
                elif dur_unit == "hours":
                    dur_sec = val * 3600
                else:
                    dur_sec = val
            elif start and end:
                dur_sec = (end - start).total_seconds()

            if dur_sec < 0:
                dur_sec = abs(dur_sec)

            if start and not end and dur_sec > 0:
                from datetime import timedelta
                end = start + timedelta(seconds=dur_sec)
            elif start and not end:
                end = start

            equip_raw = str(row[equip_col]).strip() if equip_col < len(row) and row[equip_col] is not None else "Unknown"
            if equip_raw.lower() in ("nan", "none", ""):
                equip_raw = "Unknown"

            line_raw = ""
            if line_col is not None and line_col < len(row) and row[line_col] is not None:
                line_raw = str(row[line_col]).strip()
            line_id = normalize_line_id(line_raw) if line_raw else fallback_line

            loss_raw = ""
            if loss_col is not None and loss_col < len(row) and row[loss_col] is not None:
                loss_raw = str(row[loss_col]).strip().lower()

            notes = None
            if notes_col is not None and notes_col < len(row) and row[notes_col] is not None:
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
                equipment_id=None,
                equipment_raw_name=equip_raw,
                event_type="downtime",
                loss_type=loss_raw or "availability_loss",
                is_equipment_fault=True,
                notes=notes,
            ))
        except Exception:
            bad += 1

    if len(rows) > 0 and bad / len(rows) > 0.5:
        raise ParseError(f"Too many bad rows: {bad}/{len(rows)}")

    events.sort(key=lambda e: e.start_time)
    return events


def _parse_oee_from_schema(
    headers: list[str],
    rows: list[list[Any]],
    schema: dict,
    filename: str,
    fallback_line: str,
) -> list[OEEInterval]:
    """Parse flat OEE data using AI-detected schema."""
    ts_col = _find_col(headers, schema, "timestamp")
    line_col = _find_col(headers, schema, "line")
    oee_col = _find_col(headers, schema, "oee")
    avail_col = _find_col(headers, schema, "availability")
    perf_col = _find_col(headers, schema, "performance")
    qual_col = _find_col(headers, schema, "quality")
    mtbf_col = _find_col(headers, schema, "mtbf")
    mttr_col = _find_col(headers, schema, "mttr")
    total_col = _find_col(headers, schema, "total_units")
    good_col = _find_col(headers, schema, "good_units")
    bad_col = _find_col(headers, schema, "bad_units")
    dt_col = _find_col(headers, schema, "downtime_seconds")
    int_col = _find_col(headers, schema, "interval_seconds")

    if ts_col is None:
        raise ParseError(f"No timestamp column detected in {filename}")

    def _safe(row, col):
        if col is None or col >= len(row):
            return None
        return row[col]

    def _pct(val):
        v = _to_float(val)
        if v is None:
            return None
        return v / 100.0 if v > 1.0 else v

    records: list[OEEInterval] = []
    for row in rows:
        try:
            ts = _to_datetime(_safe(row, ts_col))
            if ts is None:
                continue

            line_raw = ""
            if line_col is not None:
                lr = _safe(row, line_col)
                if lr is not None:
                    line_raw = str(lr).strip()
            line_id = normalize_line_id(line_raw) if line_raw else fallback_line

            avail = _pct(_safe(row, avail_col))
            perf = _pct(_safe(row, perf_col))
            qual = _pct(_safe(row, qual_col))
            oee = _pct(_safe(row, oee_col))
            if oee is None and avail is not None and perf is not None and qual is not None:
                oee = avail * perf * qual

            interval = _to_float(_safe(row, int_col)) or 3600.0
            total = _to_int(_safe(row, total_col))
            cph = float(total) / (interval / 3600.0) if interval > 0 and total else 0.0

            records.append(OEEInterval(
                timestamp=ts,
                line_id=line_id,
                line_raw_name=line_raw or line_id,
                availability=avail,
                performance=perf,
                quality=qual,
                oee=oee,
                mtbf_minutes=_to_float(_safe(row, mtbf_col)),
                mttr_minutes=_to_float(_safe(row, mttr_col)),
                total_units=total,
                good_units=_to_int(_safe(row, good_col)),
                bad_units=_to_int(_safe(row, bad_col)),
                downtime_seconds=_to_float(_safe(row, dt_col)) or 0.0,
                interval_seconds=interval,
                cases_per_hour=cph,
            ))
        except Exception:
            continue

    records.sort(key=lambda r: r.timestamp)
    return records


def _parse_pivot_oee_from_schema(
    headers: list[str],
    rows: list[list[Any]],
    schema: dict,
    filename: str,
    fallback_line: str,
) -> list[OEEInterval]:
    """Parse pivot/crosstab OEE data using AI-detected schema."""
    pivot_info = schema.get("pivot_info", {})

    # Find the key columns from pivot_info or column roles
    group_col = None
    metric_col = None
    value_col = None

    # Try pivot_info first
    for col_name in [pivot_info.get("group_column", "")]:
        if col_name:
            try:
                group_col = headers.index(col_name)
            except ValueError:
                pass
    for col_name in [pivot_info.get("metric_column", "")]:
        if col_name:
            try:
                metric_col = headers.index(col_name)
            except ValueError:
                pass
    for col_name in [pivot_info.get("value_column", "")]:
        if col_name:
            try:
                value_col = headers.index(col_name)
            except ValueError:
                pass

    # Fall back to column roles
    if group_col is None:
        group_col = _find_col(headers, schema, "group_key") or _find_col(headers, schema, "timestamp")
    if metric_col is None:
        metric_col = _find_col(headers, schema, "metric_name")
    if value_col is None:
        value_col = _find_col(headers, schema, "metric_value")

    line_col = _find_col(headers, schema, "line") or _find_col(headers, schema, "group_label")

    if group_col is None or metric_col is None or value_col is None:
        raise ParseError(f"Cannot identify pivot columns in {filename}")

    # Metric name normalization
    _METRIC_MAP = {
        "availability": "availability", "avail": "availability",
        "performance": "performance", "perf": "performance",
        "quality": "quality", "qual": "quality",
        "oee": "oee", "overall": "oee",
        "mtbf": "mtbf", "mttr": "mttr",
    }

    from collections import defaultdict
    groups: dict[str, dict[str, float | None]] = defaultdict(dict)
    group_lines: dict[str, str] = {}

    for row in rows:
        ts_raw = row[group_col] if group_col < len(row) else None
        metric_raw = row[metric_col] if metric_col < len(row) else None
        val_raw = row[value_col] if value_col < len(row) else None

        if ts_raw is None or metric_raw is None:
            continue

        ts_key = str(ts_raw)
        metric_str = str(metric_raw).strip().lower().replace(" ", "")

        mapped = None
        for prefix, canonical in _METRIC_MAP.items():
            if metric_str.startswith(prefix):
                mapped = canonical
                break

        if mapped:
            groups[ts_key][mapped] = _to_float(val_raw)

        if line_col is not None and line_col < len(row) and row[line_col]:
            line_raw = str(row[line_col]).strip()
            if line_raw and ts_key not in group_lines:
                group_lines[ts_key] = line_raw

    def _norm_pct(v):
        if v is None:
            return None
        return v / 100.0 if v > 1.0 else v

    records: list[OEEInterval] = []
    for ts_key, metrics in groups.items():
        ts = _to_datetime(ts_key)
        if ts is None:
            continue

        avail = _norm_pct(metrics.get("availability"))
        perf = _norm_pct(metrics.get("performance"))
        qual = _norm_pct(metrics.get("quality"))
        oee = _norm_pct(metrics.get("oee"))
        if oee is None and avail is not None and perf is not None and qual is not None:
            oee = avail * perf * qual

        line_raw = group_lines.get(ts_key, "")
        line_id = normalize_line_id(line_raw) if line_raw else fallback_line

        records.append(OEEInterval(
            timestamp=ts,
            line_id=line_id,
            line_raw_name=line_raw or line_id,
            availability=avail,
            performance=perf,
            quality=qual,
            oee=oee,
            mtbf_minutes=metrics.get("mtbf"),
            mttr_minutes=metrics.get("mttr"),
            total_units=0,
            good_units=0,
            bad_units=0,
            downtime_seconds=0.0,
            interval_seconds=3600.0,
            cases_per_hour=0.0,
        ))

    records.sort(key=lambda r: r.timestamp)
    return records
