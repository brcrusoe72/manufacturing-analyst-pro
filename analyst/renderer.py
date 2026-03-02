"""Piece E: PDF Renderer — 2-page report, clean and concise."""
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
    """Render 2-page PDF: analysis + fixes."""
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
    """Build the FPDF object. Shared by render_pdf and render_pdf_bytes."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ImportError("fpdf2 required: pip install fpdf2") from exc

    q = question or "What is costing this line the most production?"
    ts = datetime.now(timezone.utc)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=20, top=15, right=20)
    font = _register_fonts(pdf)
    blue = (25, 85, 170)

    # ── Page 1: Production Analysis ──
    pdf.add_page()

    pdf.set_font(font, "B", 14)
    pdf.set_text_color(*blue)
    pdf.cell(0, 8, "Production Analysis", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "", 9)
    pdf.set_text_color(100, 100, 100)
    d0, d1 = result.date_range
    pdf.cell(0, 4, f"Line: {result.line_id}  |  {d0.date()} to {d1.date()}  |  {ts.date().isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, f"Q: {q}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── The Story ──
    # Lead paragraph (verdict/headline)
    pdf.set_font(font, "B", 11)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 5.5, narrative.verdict)
    pdf.ln(3)

    # Body paragraphs — flowing narrative
    pdf.set_font(font, "", 10.5)
    pdf.set_text_color(30, 30, 30)
    for para in narrative.evidence_paragraphs:
        if not para.strip():
            continue
        clean = " ".join(line.strip() for line in para.split("\n") if line.strip())
        pdf.multi_cell(0, 5.5, clean)
        pdf.ln(3)

    # ── Supporting Data (continues on same page) ──
    pdf.ln(1)
    pdf.set_font(font, "B", 11)
    pdf.set_text_color(*blue)
    pdf.cell(0, 7, f"Supporting Data", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # Equipment table
    # Available width = 170mm
    headers = ["Equipment", "Events", "Hours", "MTBF(m)", "Repeat%", "1st", "2nd", "3rd"]
    widths = [46, 16, 14, 16, 16, 21, 21, 20]  # total = 170mm
    pdf.set_font(font, "B", 9)
    pdf.set_fill_color(230, 236, 247)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font(font, "", 9)
    pdf.set_text_color(20, 20, 20)
    for ep in result.equipment_profiles[:15]:
        name = ep.equipment_raw_name[:24]
        mtbf = f"{ep.mtbf_minutes:.1f}" if ep.mtbf_minutes else "-"
        repeat = f"{ep.repeat_failure_rate:.0%}"
        s1 = ep.by_shift.get("1st", {})
        s2 = ep.by_shift.get("2nd", {})
        s3 = ep.by_shift.get("3rd", {})
        row = [
            name,
            f"{ep.event_count:,}",
            f"{ep.total_downtime_hours:.1f}",
            mtbf,
            repeat,
            f"{s1.get('count', 0):,} / {s1.get('hours', 0):.0f}h",
            f"{s2.get('count', 0):,} / {s2.get('hours', 0):.0f}h",
            f"{s3.get('count', 0):,} / {s3.get('hours', 0):.0f}h",
        ]
        for val, w in zip(row, widths):
            align = "L" if val == name else "C"
            pdf.cell(w, 5.5, val, border=1, align=align)
        pdf.ln()

    pdf.ln(2)

    # Shift comparison table
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(*blue)
    pdf.cell(0, 6, "Shift Comparison", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)

    # Available width = 210 - 20 - 20 = 170mm
    s_headers = ["Shift", "OEE", "Events", "Down(h)", "Unassign%", "Startup", "Recov(m)"]
    s_widths = [20, 22, 24, 24, 26, 26, 28]  # total = 170mm
    pdf.set_font(font, "B", 8)
    for h, w in zip(s_headers, s_widths):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font(font, "", 8)
    pdf.set_text_color(20, 20, 20)
    for sp in result.shift_profiles:
        oee_val = f"{sp.avg_oee:.1%}" if sp.avg_oee else "N/A"
        if sp.startup_penalty_points is not None:
            startup = f"{sp.startup_penalty_points:+.1f}pp"
        else:
            startup = "N/A"
        row = [
            sp.shift,
            oee_val,
            f"{sp.event_count:,}",
            f"{sp.total_downtime_hours:.1f}",
            f"{sp.unassigned_rate:.1%}",
            startup,
            f"{sp.avg_recovery_minutes:.1f}",
        ]
        for val, w in zip(row, s_widths):
            pdf.cell(w, 5.5, val, border=1, align="C")
        pdf.ln()

    # ── Page 3 (optional): Root Cause & Fixes ──
    if fixes:
        pdf.add_page()
        pdf.set_font(font, "B", 14)
        pdf.set_text_color(*blue)
        pdf.cell(0, 8, "Root Cause Analysis & Recommended Fixes", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for i, fix in enumerate(fixes, 1):
            # Equipment header
            pdf.set_font(font, "B", 10)
            pdf.set_text_color(*blue)
            pdf.cell(0, 6, f"{i}. {fix.equipment_name}", new_x="LMARGIN", new_y="NEXT")

            # Likely cause
            pdf.set_font(font, "", 9)
            pdf.set_text_color(20, 20, 20)
            _safe_multi(pdf, 0, 4.5, f"Likely cause: {fix.likely_cause}")
            pdf.ln(0.5)

            # Root causes
            clean_rcs = [rc.strip() for rc in fix.root_causes if rc.strip()]
            if clean_rcs:
                pdf.set_font(font, "B", 9)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4.5, "Root causes:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 9)
                pdf.set_text_color(20, 20, 20)
                for j, rc in enumerate(clean_rcs[:3], 1):
                    _safe_multi(pdf, 0, 4.2, f"{j}. {rc}")
                pdf.ln(0.5)

            # Fixes
            clean_fixes = [f.strip() for f in fix.fixes if f.strip()]
            if clean_fixes:
                pdf.set_font(font, "B", 9)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4.5, "Corrective actions:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 9)
                pdf.set_text_color(20, 20, 20)
                for j, action in enumerate(clean_fixes[:3], 1):
                    _safe_multi(pdf, 0, 4.2, f"{j}. {action}")
                pdf.ln(0.5)

            # PM additions
            clean_pm = [pm.strip() for pm in fix.pm_additions if pm.strip()]
            if clean_pm:
                pdf.set_font(font, "B", 9)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 4.5, "Add to PM schedule:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 9)
                pdf.set_text_color(20, 20, 20)
                for pm in clean_pm[:3]:
                    _safe_multi(pdf, 0, 4.2, f"- {pm}")

            pdf.ln(3)

    return pdf


def _safe_multi(pdf: Any, w: float, h: float, text: str) -> None:
    """multi_cell that won't crash on edge cases."""
    if not text or not text.strip():
        return
    try:
        pdf.multi_cell(w, h, text)
    except Exception:
        # If text is too long for remaining page space, add a page and retry
        try:
            pdf.add_page()
            pdf.multi_cell(w, h, text)
        except Exception:
            pass  # Skip this item rather than crash


def _section(pdf: Any, title: str, color: tuple[int, int, int], font: str) -> None:
    pdf.set_text_color(*color)
    pdf.set_font(font, "B", 10)
    pdf.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")


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
    # Clean, short filename — no question slug
    return f"{clean_line}_Analysis_{ts.date().isoformat()}.pdf"
