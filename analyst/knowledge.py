"""Build equipment knowledge base from passdown data — no LLM, pure aggregation.

Reads passdown.json → produces equipment_kb.json with:
  - Per-equipment failure profiles (frequency, total minutes, recurring issues)
  - Known fixes and their outcomes
  - Open vs resolved tracking
  - Shift patterns
  - Supervisor observations (verbatim quotes worth citing)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class FixRecord:
    action: str
    result: str
    root_cause: str
    count: int = 1


@dataclass(slots=True)
class EquipmentKB:
    area: str
    event_count: int
    total_minutes: int
    avg_minutes: float
    lines_affected: list[int | str]
    by_shift: dict[str, int]
    by_line: dict[str, int]
    recurring_issues: list[dict]       # [{issue, count, example_dates}]
    known_fixes: list[dict]            # [{action, result, root_cause, count}]
    open_issues: list[dict]            # [{issue, date, line, shift}]
    notable_quotes: list[dict]         # [{text, date, line, context}]
    products_affected: list[str]
    resolution_rate: float             # fraction resolved


def _normalize_area(area: str) -> str:
    """Normalize equipment area names for grouping."""
    area = area.strip()
    # Common normalizations
    mappings = {
        'bear labeler': 'Bear Labeler',
        'labeler a': 'Labeler',
        'labeler b': 'Labeler',
        'tray packer': 'Tray Packer',
        'shrink tunnel': 'Shrink Tunnel',
        'shrink wrapper': 'Shrink Wrapper',
        'shrink tunnel - kayat': 'Shrink Tunnel',
        'video jet print and apply': 'Video Jet Print & Apply',
        'videojet print and apply': 'Video Jet Print & Apply',
        'diagraph print and apply': 'Diagraph Print & Apply',
        'print and apply': 'Print & Apply',
        'ryson spiral': 'Ryson Spiral',
        'pallet wrapper': 'Pallet Wrapper',
        'palletizer': 'Palletizer',
        'palletizer - alvey': 'Palletizer',
        'conveyers': 'Conveyors',
        'conveyors': 'Conveyors',
        'conveyor problem': 'Conveyors',
        'case conveyor': 'Case Conveyor',
        'can conveyor': 'Can Conveyor',
        'depal': 'Depalletizer',
        'depal other': 'Depalletizer',
        'x-ray machine': 'X-Ray Machine',
        'riverwood': 'Riverwood',
        'start up': 'Start-up',
        'start-up': 'Start-up',
        'set-up': 'Set-up',
        'changeover': 'Changeover',
        'change over': 'Changeover',
        'lunch & breaks': 'Lunch & Breaks',
        'lunch (comida)': 'Lunch & Breaks',
        'breaks/lunch/meals': 'Lunch & Breaks',
        'labor': 'Labor',
        'accumulation table': 'Accumulation Table',
        'product quality': 'Product Quality',
        'quality event': 'Quality Event',
        'date code change': 'Date Code Change',
    }
    return mappings.get(area.lower(), area)


def _fingerprint_issue(issue: str) -> str:
    """Create a fuzzy key for grouping similar issues."""
    s = issue.lower().strip()
    s = re.sub(r'[^a-z0-9 ]', '', s)
    # Remove common filler words
    for w in ['the', 'a', 'an', 'is', 'was', 'were', 'are', 'been', 'being',
              'throughout', 'during', 'shift', 'line', 'machine']:
        s = re.sub(rf'\b{w}\b', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Truncate to first 40 chars for grouping
    return s[:40]


def _is_notable_quote(event: dict) -> bool:
    """Identify supervisor observations worth preserving verbatim."""
    text = event.get('issue', '') + ' ' + event.get('root_cause', '')
    text = text.lower()
    # Look for specific, insightful observations
    indicators = [
        "maintenance states", "maintenance said", "maintenance don't know",
        "root cause wasn't located", "issue ongoing", "has been an issue",
        "we don't have", "we're out of", "unable to resolve",
        "multiple times", "throughout shift", "entire shift",
        "no one came", "waiting for", "short mech", "short staff",
        "work around", "workaround",
    ]
    return any(ind in text for ind in indicators)


def _is_resolved(event: dict) -> bool:
    """Check if event was resolved."""
    rc = (event.get('root_cause', '') + ' ' + event.get('result', '')).lower()
    if 'resolved' in rc or 'repaired' in rc or 'fixed' in rc:
        return True
    if 'ongoing' in rc or 'open' in rc or 'unresolved' in rc or 'unable' in rc:
        return False
    # If result says "line running" and no "ongoing", treat as resolved
    if 'line running' in rc and 'ongoing' not in rc:
        return True
    return False  # default to unresolved


def build_knowledge_base(passdown_path: str | Path) -> dict:
    """Build equipment knowledge base from passdown JSON."""
    data = json.loads(Path(passdown_path).read_text())

    # Collect all events grouped by normalized area
    by_area: dict[str, list[dict]] = defaultdict(list)

    for block in data['blocks']:
        for evt in block['events']:
            area = _normalize_area(evt['area'])
            evt_copy = dict(evt)
            evt_copy['_block_product'] = block.get('product', '')
            evt_copy['_block_cases'] = block.get('cases')
            evt_copy['_block_oee'] = block.get('oee')
            by_area[area].append(evt_copy)

    # Build KB per area
    equipment_kb: list[dict] = []

    for area, events in sorted(by_area.items(), key=lambda x: -len(x[1])):
        total_min = sum(e.get('duration_minutes') or 0 for e in events)
        count = len(events)
        avg_min = total_min / count if count else 0

        # Lines and shifts
        lines = sorted(set(e['line'] for e in events if e.get('line')))
        shift_counts = Counter(e['shift'] for e in events if e.get('shift'))
        line_counts = Counter(str(e['line']) for e in events if e.get('line'))

        # Products
        products = sorted(set(
            e['_block_product'] for e in events
            if e.get('_block_product')
        ))[:10]

        # Recurring issues — group by fingerprint
        issue_groups: dict[str, list[dict]] = defaultdict(list)
        for e in events:
            if e.get('issue'):
                fp = _fingerprint_issue(e['issue'])
                if fp:
                    issue_groups[fp].append(e)

        recurring = []
        for fp, group in sorted(issue_groups.items(), key=lambda x: -len(x[1])):
            if len(group) >= 2:  # only if it recurs
                example_dates = sorted(set(e['date'] for e in group if e.get('date')))[:5]
                recurring.append({
                    'issue': group[0]['issue'][:200],
                    'count': len(group),
                    'example_dates': example_dates,
                })
        recurring = recurring[:10]

        # Known fixes — deduplicate by action text
        fix_groups: dict[str, dict] = {}
        for e in events:
            action = e.get('action', '').strip()
            if not action:
                continue
            key = action[:80].lower()
            if key not in fix_groups:
                fix_groups[key] = {
                    'action': action[:200],
                    'result': e.get('result', '')[:200],
                    'root_cause': e.get('root_cause', '')[:200],
                    'count': 1,
                }
            else:
                fix_groups[key]['count'] += 1

        known_fixes = sorted(fix_groups.values(), key=lambda x: -x['count'])[:8]

        # Open issues (most recent unresolved)
        open_issues = []
        for e in sorted(events, key=lambda x: x.get('date', ''), reverse=True):
            if not _is_resolved(e) and e.get('issue'):
                open_issues.append({
                    'issue': e['issue'][:200],
                    'date': e.get('date', ''),
                    'line': e.get('line', ''),
                    'shift': e.get('shift', ''),
                })
            if len(open_issues) >= 5:
                break

        # Notable quotes
        notable = []
        for e in events:
            if _is_notable_quote(e):
                text = e.get('issue', '')
                if e.get('root_cause'):
                    text += ' | RC: ' + e['root_cause']
                if e.get('notes'):
                    text += ' | Note: ' + e['notes']
                notable.append({
                    'text': text[:300],
                    'date': e.get('date', ''),
                    'line': e.get('line', ''),
                    'context': e.get('_block_product', ''),
                })
            if len(notable) >= 8:
                break

        # Resolution rate
        resolved_count = sum(1 for e in events if _is_resolved(e))
        resolution_rate = resolved_count / count if count else 0

        equipment_kb.append({
            'area': area,
            'event_count': count,
            'total_minutes': total_min,
            'avg_minutes': round(avg_min, 1),
            'lines_affected': lines,
            'by_shift': dict(shift_counts),
            'by_line': dict(line_counts),
            'recurring_issues': recurring,
            'known_fixes': known_fixes,
            'open_issues': open_issues,
            'notable_quotes': notable,
            'products_affected': products,
            'resolution_rate': round(resolution_rate, 2),
        })

    # Build output
    kb = {
        'meta': {
            'source': 'passdown_full.xlsx',
            'date_range': data['meta']['date_range'],
            'total_events': data['meta']['total_events'],
            'equipment_categories': len(equipment_kb),
        },
        'rates': data.get('rates', []),
        'equipment': equipment_kb,
    }

    return kb


def save_knowledge_base(
    passdown_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Build and save equipment knowledge base."""
    kb = build_knowledge_base(passdown_path)

    if output_path is None:
        output_path = Path(passdown_path).parent / 'equipment_kb.json'
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(kb, indent=2, ensure_ascii=False))
    return output_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m analyst.knowledge <passdown.json> [output.json]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    out = save_knowledge_base(src, dst)

    kb = build_knowledge_base(src)
    print(f"Equipment categories: {kb['meta']['equipment_categories']}")
    print(f"Total events: {kb['meta']['total_events']}")
    print(f"\nTop 10 by frequency:")
    for eq in kb['equipment'][:10]:
        print(f"  {eq['area']}: {eq['event_count']} events, {eq['total_minutes']} min, "
              f"resolution {eq['resolution_rate']:.0%}, "
              f"recurring: {len(eq['recurring_issues'])}")
    print(f"\nSaved to: {out}")
