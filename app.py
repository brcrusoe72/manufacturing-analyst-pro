"""Manufacturing Analyst Pro — Web Application.

Upload your production data. Get intelligent analysis. Data never stored.
"""
from __future__ import annotations

import streamlit as st
import time

# ── Page Config ──
st.set_page_config(
    page_title="Manufacturing Analyst Pro",
    page_icon="🏭",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .stApp { max-width: 900px; margin: 0 auto; }
    .big-header { font-size: 2.2rem; font-weight: 700; color: #1955AA; margin-bottom: 0; }
    .sub-header { font-size: 1.1rem; color: #666; margin-top: 0; margin-bottom: 2rem; }
    .privacy-badge {
        background: #E8F5E9; border: 1px solid #4CAF50; border-radius: 8px;
        padding: 8px 16px; display: inline-block; font-size: 0.85rem; color: #2E7D32;
    }
    .metric-card {
        background: #F5F7FA; border-radius: 8px; padding: 12px 16px;
        border-left: 4px solid #1955AA;
    }
    .tier-badge-free { background: #E3F2FD; color: #1565C0; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    .tier-badge-pro { background: #FFF3E0; color: #E65100; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ── Session State Init ──
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "pro_key" not in st.session_state:
    st.session_state.pro_key = None


def _is_pro() -> bool:
    """Check if user has Pro access."""
    return st.session_state.pro_key is not None and st.session_state.pro_key.strip() != ""


# ── Header ──
st.markdown('<p class="big-header">🏭 Manufacturing Analyst Pro</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Your production data is telling you where you\'re bleeding money. '
    'You\'re not hearing it.</p>',
    unsafe_allow_html=True,
)

# Privacy badge
st.markdown(
    '<div class="privacy-badge">🔒 Your data is processed in memory and immediately discarded. '
    'Nothing is stored. Ever.</div>',
    unsafe_allow_html=True,
)
st.markdown("")

# ── Pro Key (sidebar) ──
with st.sidebar:
    st.markdown("### 🔑 Pro Access")
    pro_input = st.text_input(
        "Enter your Pro key",
        type="password",
        value=st.session_state.pro_key or "",
        help="Get a Pro key at the pricing section below",
    )
    if pro_input != (st.session_state.pro_key or ""):
        st.session_state.pro_key = pro_input if pro_input.strip() else None
        st.rerun()

    if _is_pro():
        st.success("✅ Pro features unlocked")
    else:
        st.info("Free tier: narrative analysis included")

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    question = st.text_area(
        "Analysis question",
        value="What is costing this line the most production, and what should we fix first?",
        height=80,
        help="The question your report will answer",
    )

    company_name = None
    if _is_pro():
        company_name = st.text_input("Company name (optional)", help="Appears on PDF header")

# ── Upload Section ──
st.markdown("### 📁 Upload Your Data")

col1, col2 = st.columns([3, 1])
with col1:
    uploaded_files = st.file_uploader(
        "Drop your MES export files here",
        type=["xlsx", "xls", "csv", "tsv"],
        accept_multiple_files=True,
        help="Supports: Traksys exports, generic CSV/Excel with timestamp + equipment + duration columns",
    )
with col2:
    st.markdown("")
    st.markdown("")

if uploaded_files:
    # Show detected formats
    with st.expander("📋 Detected file formats", expanded=True):
        for f in uploaded_files:
            st.markdown(f"- **{f.name}** ({f.size / 1024:.0f} KB)")

# ── How It Works ──
if not uploaded_files:
    st.markdown("---")
    st.markdown("### How it works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**1. Upload** 📤")
        st.markdown("Drop your MES downtime export, OEE report, or any CSV with equipment & duration data.")
    with c2:
        st.markdown("**2. Analyze** ⚡")
        st.markdown("AI reads your data like a senior plant engineer — equipment patterns, shift comparisons, root causes.")
    with c3:
        st.markdown("**3. Download** 📄")
        st.markdown("Get a PDF report that names specific equipment, specific shifts, and one clear recommendation.")

    st.markdown("---")
    st.markdown("### Supported Formats")
    st.markdown("""
    - **Traksys MES** — Event Overview & OEE Overview exports (auto-detected)
    - **Generic CSV/Excel** — Any file with columns like: date, equipment/machine, duration
    - **Multiple files** — Upload event + OEE files together for richer analysis
    """)

# ── Analysis ──
if uploaded_files:
    analyze_btn = st.button(
        "🔍 Analyze My Data",
        type="primary",
        use_container_width=True,
    )

    if analyze_btn:
        t0 = time.time()

        # Progress
        progress = st.progress(0, text="Loading data...")

        try:
            # Load
            from analyst.web_loader import load_multiple_files

            files = [(f, f.name) for f in uploaded_files]
            events, oee, descriptions = load_multiple_files(files)
            progress.progress(20, text=f"Loaded {len(events):,} events, {len(oee):,} OEE intervals...")

            if not events and not oee:
                st.error("No parseable data found. Check that your files have columns for timestamps, equipment, and duration.")
                st.stop()

            # Show what was detected
            for desc in descriptions:
                st.info(f"📊 {desc}")

            # Analyze
            progress.progress(35, text="Running analysis engine...")
            from analyst.engine import analyze
            result = analyze(events, oee)

            progress.progress(50, text="Generating narrative (this takes ~30-60 seconds)...")

            # Narrative
            from analyst.narrative import generate_narrative
            narrative = generate_narrative(result, question)

            progress.progress(75, text="Preparing report...")

            # Fixes (Pro only)
            fixes = []
            if _is_pro():
                progress.progress(80, text="Researching root causes and fixes (Pro)...")
                from analyst.researcher import research_fixes
                from analyst.static_kb import format_kb_for_prompt

                operational_names = {"unassigned", "not scheduled", "unknown", "short stop",
                                     "change over", "break-lunch", "breaks/lunch/meals",
                                     "breaks, lunch, meals", "break relief other line",
                                     "training - meeting", "meetings", "other", "holiday",
                                     "no stock", "bad stock", "drive off", "power outage"}
                real_equipment = [
                    ep for ep in result.equipment_profiles
                    if ep.equipment_raw_name.lower().strip() not in operational_names and ep.equipment_id is not None
                ]
                fixes = research_fixes(real_equipment[:3])

            # Render PDF
            progress.progress(90, text="Rendering PDF...")
            from analyst.renderer import render_pdf_bytes
            pdf_bytes, pdf_filename = render_pdf_bytes(
                result, narrative, fixes,
                question=question,
                company_name=company_name,
            )

            elapsed = time.time() - t0
            progress.progress(100, text=f"Done in {elapsed:.1f} seconds")
            time.sleep(0.5)
            progress.empty()

            # ── Results ──
            st.markdown("---")
            st.markdown("## 📋 Analysis Results")

            # Key metrics
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.metric("Total Events", f"{result.total_events:,}")
            with mc2:
                st.metric("Downtime", f"{result.total_downtime_hours:.0f}h")
            with mc3:
                oee_str = f"{result.avg_oee:.1%}" if result.avg_oee else "N/A"
                st.metric("Avg OEE", oee_str)
            with mc4:
                st.metric("Top Loss", result.top_loss_driver[:20])

            # Narrative preview
            st.markdown("### The Analysis")
            st.markdown(f"**{narrative.verdict}**")
            for para in narrative.evidence_paragraphs:
                st.markdown(para)

            # Download
            st.markdown("---")
            tier_label = "Pro Report" if _is_pro() else "Free Report"
            st.download_button(
                label=f"📥 Download PDF ({tier_label})",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

            # Pro upsell for free users
            if not _is_pro():
                st.markdown("---")
                st.markdown(
                    "### 🚀 Want root causes, fixes, and trend memory?"
                )
                st.markdown(
                    "**Pro** includes: specific root cause analysis for your top 3 equipment issues, "
                    "actionable corrective actions, PM schedule additions, and memory across uploads "
                    "so you can track whether your fixes are working."
                )
                st.markdown("**$149/month** — [Get Pro Access →](#pricing)")

            # Equipment table
            if result.equipment_profiles:
                st.markdown("### Equipment Breakdown")
                import pandas as pd
                equip_data = []
                for ep in result.equipment_profiles[:15]:
                    equip_data.append({
                        "Equipment": ep.equipment_raw_name[:30],
                        "Events": ep.event_count,
                        "Hours": round(ep.total_downtime_hours, 1),
                        "MTBF (min)": round(ep.mtbf_minutes, 1) if ep.mtbf_minutes else None,
                        "Repeat %": f"{ep.repeat_failure_rate:.0%}",
                        "1st": ep.by_shift.get("1st", {}).get("count", 0),
                        "2nd": ep.by_shift.get("2nd", {}).get("count", 0),
                        "3rd": ep.by_shift.get("3rd", {}).get("count", 0),
                    })
                st.dataframe(pd.DataFrame(equip_data), use_container_width=True, hide_index=True)

            # Save results to session state
            st.session_state.analysis_done = True
            st.session_state.last_result = result
            st.session_state.last_narrative = narrative
            st.session_state.last_fixes = fixes

        except ValueError as e:
            progress.empty()
            st.error(f"⚠️ {str(e)}")
        except Exception as e:
            progress.empty()
            st.error(f"❌ Analysis failed: {str(e)}")
            import traceback
            with st.expander("Error details"):
                st.code(traceback.format_exc())


# ── Pricing Section ──
st.markdown("---")
st.markdown('<a id="pricing"></a>', unsafe_allow_html=True)
st.markdown("## Pricing")

p1, p2, p3 = st.columns(3)

with p1:
    st.markdown("### Free")
    st.markdown("**$0/month**")
    st.markdown("""
    - ✅ Narrative analysis
    - ✅ Equipment breakdown table
    - ✅ Shift comparison
    - ✅ PDF download
    - ❌ Root cause analysis
    - ❌ Corrective actions
    - ❌ Memory across uploads
    - 3 reports/month
    """)

with p2:
    st.markdown("### Pro")
    st.markdown("**$149/month**")
    st.markdown("""
    - ✅ Everything in Free
    - ✅ Root cause analysis (top 3 equipment)
    - ✅ Specific corrective actions
    - ✅ PM schedule additions
    - ✅ Memory across uploads
    - ✅ Company branding on reports
    - ✅ Unlimited reports
    """)
    st.link_button("Get Pro →", "https://buy.stripe.com/placeholder", type="primary", use_container_width=True)

with p3:
    st.markdown("### Enterprise")
    st.markdown("**$499/month**")
    st.markdown("""
    - ✅ Everything in Pro
    - ✅ API access
    - ✅ Multi-line comparison
    - ✅ Custom equipment dictionaries
    - ✅ Custom shift definitions
    - ✅ Webhook delivery
    - ✅ Priority support
    """)
    st.link_button("Contact Us →", "mailto:bri@crusoeanalytics.com", use_container_width=True)


# ── Footer ──
st.markdown("---")
fc1, fc2 = st.columns(2)
with fc1:
    st.markdown(
        "Built by a production supervisor who's run the lines. "
        "8+ years in food manufacturing. Six Sigma Black Belt."
    )
with fc2:
    st.markdown(
        "🔒 **Privacy:** Your data is processed in memory and immediately discarded. "
        "No data is stored, logged, or shared. Ever."
    )
st.markdown(
    '<div style="text-align: center; color: #999; font-size: 0.8rem; margin-top: 1rem;">'
    'Manufacturing Analyst Pro — The engineer who reads your data.'
    '</div>',
    unsafe_allow_html=True,
)
