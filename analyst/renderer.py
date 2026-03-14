"""Piece E: PDF Renderer — compact report, minimal whitespace."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import AnalysisResult
from .narrative import Narrative
from .researcher import EquipmentFix


def render_pdf_bytes(
    result: AnalysisResult,
    narrative: Narrative,
    fixes: list[EquipmentFix],
    *,
    question: str | None = None,
    company_name: str | None = None,
) -> tuple[bytes, str]:
    """Render PDF and return (pdf_bytes, filename). For web use."""
    import io
    q = question or "What is costing this line the most production?"
    ts = datetime.now(timezone.utc)
    filename = _make_filename(result.line_id, q, ts)
    pdf = _build_pdf(result, narrative, fixes, question=q, company_name=company_name)
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue(), filename


def render_pdf(
    result: AnalysisResult,
    narrative: Narrative,
    fixes: list[EquipmentFix],
    output_dir: str | Path,
    *,
    question: str | None = None,
) -> Path:
    """Render PDF to file."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ImportError("fpdf2 required: pip install fpdf2") from exc

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    q = question or "What is costing this line the most production?"
    ts = datetime.now(timezone.utc)
    filename = _make_filename(result.line_id, q, ts)
    out_path = out_dir / filename

    pdf = _build_pdf(result, narrative, fixes, question=q)
    pdf.output(str(out_path))
    return out_path


def _build_pdf(
    result: AnalysisResult,
    narrative: Narrative,
    fixes: list[EquipmentFix],
    *,
    question: str | None = None,
    company_name: str | None = None,
) -> Any:
    """Build the FPDF object."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ImportError("fpdf2 required: pip install fpdf2") from exc

    q = question or "What is costing this line the most production?"
    ts = datetime.now(timezone.utc)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(left=15, top=12, right=15)
    font = _register_fonts(pdf)
    W = 180  # usable width = 210 - 15 - 15
    blue = (25, 85, 170)
    black = (20, 20, 20)
    gray = (100, 100, 100)

    # ════════════════════════════════════════════
    # PAGE 1: Analysis
    # ════════════════════════════════════════════
    pdf.add_page()

    # Header
    pdf.set_font(font, "B", 13)
    pdf.set_text_color(*blue)
    pdf.cell(0, 7, "Production Analysis", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "", 8)
    pdf.set_text_color(*gray)
    d0, d1 = result.date_range
    header_line = f"Line: {result.line_id}  |  {d0.date()} to {d1.date()}  |  {ts.date().isoformat()}"
    if company_name:
        header_line = f"{company_name}  |  {header_line}"
    pdf.cell(0, 3.5, header_line, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 3.5, f"Q: {q}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Verdict (bold lead)
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(*black)
    _write_text(pdf, narrative.verdict, 4.2)
    pdf.ln(2)

    # Body paragraphs
    pdf.set_font(font, "", 8.5)
    pdf.set_text_color(30, 30, 30)
    for para in narrative.evidence_paragraphs:
        if not para.strip():
            continue
        clean = " ".join(line.strip() for line in para.split("\n") if line.strip())
        _write_text(pdf, clean, 3.8)
        pdf.ln(1.5)

    # ── Supporting Data ──
    pdf.ln(2)
    pdf.set_font(font, "B", 10)
    pdf.set_text_color(*blue)
    pdf.cell(0, 5, "Supporting Data", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # Equipment Table
    eq_headers = ["Equipment", "Events", "Hours", "MTBF", "Repeat", "1st Shift", "2nd Shift", "3rd Shift"]
    eq_widths = [46, 15, 13, 13, 13, 27, 27, 26]
    _table_header(pdf, font, eq_headers, eq_widths)

    pdf.set_font(font, "", 7)
    pdf.set_text_color(*black)
    for ep in result.equipment_profiles[:12]:
        def _sv(d: dict) -> str:
            c, h = d.get("count", 0), d.get("hours", 0)
            return f"{c:,} ({h:.0f}h)" if c else "-"
        s1, s2, s3 = ep.by_shift.get("1st", {}), ep.by_shift.get("2nd", {}), ep.by_shift.get("3rd", {})
        row = [
            ep.equipment_raw_name[:26],
            f"{ep.event_count:,}",
            f"{ep.total_downtime_hours:.1f}",
            f"{ep.mtbf_minutes:.0f}m" if ep.mtbf_minutes else "-",
            f"{ep.repeat_failure_rate:.0%}",
            _sv(s1), _sv(s2), _sv(s3),
        ]
        for j, (val, w) in enumerate(zip(row, eq_widths)):
            pdf.cell(w, 4.5, val, border=1, align="L" if j == 0 else "C")
        pdf.ln()

    pdf.ln(3)

    # Shift Comparison Table
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(*blue)
    pdf.cell(0, 5, "Shift Comparison", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    has_oee = any(sp.avg_oee is not None for sp in result.shift_profiles)
    has_startup = any(sp.startup_penalty_points is not None for sp in result.shift_profiles)

    sh_headers = ["Shift"]
    sh_widths = [20]
    if has_oee:
        sh_headers.append("Avg OEE"); sh_widths.append(22)
    sh_headers += ["Events", "Downtime (h)", "Unassigned %"]
    sh_widths += [24, 26, 26]
    if has_startup:
        sh_headers.append("Startup Penalty"); sh_widths.append(26)
    sh_headers.append("Avg Recovery (m)"); sh_widths.append(26)
    # Scale to W
    scale = W / sum(sh_widths)
    sh_widths = [round(w * scale, 1) for w in sh_widths]

    _table_header(pdf, font, sh_headers, sh_widths)

    pdf.set_font(font, "", 8)
    pdf.set_text_color(*black)
    for sp in result.shift_profiles:
        row = [sp.shift]
        if has_oee:
            row.append(f"{sp.avg_oee:.1%}" if sp.avg_oee else "N/A")
        row += [f"{sp.event_count:,}", f"{sp.total_downtime_hours:.1f}", f"{sp.unassigned_rate:.1%}"]
        if has_startup:
            row.append(f"{sp.startup_penalty_points * 100:+.1f} pp" if sp.startup_penalty_points is not None else "N/A")
        row.append(f"{sp.avg_recovery_minutes:.1f}")
        for val, w in zip(row, sh_widths):
            pdf.cell(w, 5, val, border=1, align="C")
        pdf.ln()

    # ════════════════════════════════════════════
    # PAGE 2+ (optional): Root Cause & Fixes
    # ════════════════════════════════════════════
    if fixes:
        pdf.add_page()
        pdf.set_font(font, "B", 13)
        pdf.set_text_color(*blue)
        pdf.cell(0, 7, "Root Cause Analysis & Recommended Fixes", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for i, fix in enumerate(fixes, 1):
            # Equipment name
            pdf.set_font(font, "B", 9.5)
            pdf.set_text_color(*blue)
            pdf.cell(0, 5, f"{i}. {fix.equipment_name}", new_x="LMARGIN", new_y="NEXT")

            # Likely cause
            pdf.set_font(font, "", 8)
            pdf.set_text_color(*black)
            _write_text(pdf, f"Likely cause: {fix.likely_cause}", 3.6)
            pdf.ln(1)

            # Root causes
            clean_rcs = [rc.strip() for rc in fix.root_causes if rc.strip()]
            if clean_rcs:
                pdf.set_font(font, "B", 8)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4, "Root causes:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 8)
                pdf.set_text_color(*black)
                for j, rc in enumerate(clean_rcs[:3], 1):
                    _write_text(pdf, f"{j}. {rc}", 3.6)

            # Corrective actions
            clean_fixes = [f.strip() for f in fix.fixes if f.strip()]
            if clean_fixes:
                pdf.ln(0.5)
                pdf.set_font(font, "B", 8)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4, "Corrective actions:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 8)
                pdf.set_text_color(*black)
                for j, action in enumerate(clean_fixes[:3], 1):
                    _write_text(pdf, f"{j}. {action}", 3.6)

            # PM additions
            clean_pm = [pm.strip() for pm in fix.pm_additions if pm.strip()]
            if clean_pm:
                pdf.ln(0.5)
                pdf.set_font(font, "B", 8)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4, "Add to PM schedule:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 8)
                pdf.set_text_color(*black)
                for pm in clean_pm[:3]:
                    _write_text(pdf, f"• {pm}", 3.6)

            pdf.ln(4)

    return pdf


def _write_text(pdf: Any, text: str, line_h: float = 4.0) -> None:
    """Write text using multi_cell with left alignment (no justify stretching)."""
    if not text or not text.strip():
        return
    # Reset X to left margin to avoid "not enough horizontal space" errors
    pdf.set_x(pdf.l_margin)
    try:
        pdf.multi_cell(0, line_h, text, align="L")
    except Exception:
        # If it still fails, skip rather than crash the whole report
        pass


def _table_header(pdf: Any, font: str, headers: list[str], widths: list[float]) -> None:
    """Render a table header row."""
    pdf.set_font(font, "B", 7)
    pdf.set_fill_color(230, 236, 247)
    for h, w in zip(headers, widths):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()


def _register_fonts(pdf: Any) -> str:
    regular_candidates = [
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path.home() / ".fonts" / "DejaVuSans.ttf",
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path.home() / ".fonts" / "DejaVuSans-Bold.ttf",
    ]
    regular = next((p for p in regular_candidates if p.exists()), None)
    if regular is None:
        return "Helvetica"
    bold = next((p for p in bold_candidates if p.exists()), regular)
    pdf.add_font("DejaVu", "", str(regular))
    pdf.add_font("DejaVu", "B", str(bold))
    return "DejaVu"


def _make_filename(line_id: str, question: str, ts: datetime) -> str:
    clean_line = re.sub(r"[^a-zA-Z0-9]+", "_", line_id).strip("_") or "Line"
    return f"{clean_line}_Analysis_{ts.date().isoformat()}.pdf"
