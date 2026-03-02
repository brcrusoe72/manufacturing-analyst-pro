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
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Professional CSS ──
st.markdown("""
<style>
    /* Reset Streamlit defaults */
    .block-container { padding-top: 2rem; max-width: 1100px; }
    header[data-testid="stHeader"] { background: transparent; }
    
    /* Typography */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Hero Section */
    .hero-container {
        background: linear-gradient(135deg, #0A1628 0%, #1B3A5C 50%, #1955AA 100%);
        border-radius: 16px;
        padding: 3rem 3rem 2.5rem;
        margin-bottom: 2rem;
        color: white;
    }
    .hero-title {
        font-size: 2.6rem;
        font-weight: 700;
        line-height: 1.15;
        margin-bottom: 0.75rem;
        color: white;
    }
    .hero-subtitle {
        font-size: 1.15rem;
        color: #A8C4E0;
        line-height: 1.6;
        margin-bottom: 1.5rem;
        max-width: 650px;
    }
    .hero-stat {
        display: inline-block;
        margin-right: 2rem;
        margin-bottom: 0.5rem;
    }
    .hero-stat-number { font-size: 1.5rem; font-weight: 700; color: #5BB8F5; }
    .hero-stat-label { font-size: 0.8rem; color: #A8C4E0; text-transform: uppercase; letter-spacing: 0.05em; }
    
    /* Privacy Badge */
    .privacy-strip {
        background: #F0FDF4;
        border: 1px solid #BBF7D0;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 0.88rem;
        color: #166534;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 1.5rem;
    }
    
    /* Cards */
    .feature-card {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 1.5rem;
        height: 100%;
        transition: box-shadow 0.2s;
    }
    .feature-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    .feature-card h4 { color: #1955AA; margin-bottom: 0.5rem; font-size: 1rem; }
    .feature-card p { color: #6B7280; font-size: 0.9rem; line-height: 1.5; }
    
    /* Section Headers */
    .section-header {
        font-size: 1.6rem;
        font-weight: 700;
        color: #111827;
        margin-bottom: 0.5rem;
    }
    .section-subheader {
        font-size: 1rem;
        color: #6B7280;
        margin-bottom: 1.5rem;
    }
    
    /* Upload Zone */
    [data-testid="stFileUploader"] {
        border: 2px dashed #CBD5E1;
        border-radius: 12px;
        padding: 1rem;
        background: #F8FAFC;
    }
    [data-testid="stFileUploader"]:hover { border-color: #1955AA; }
    
    /* Metrics */
    .metric-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-box {
        flex: 1;
        background: #F8FAFC;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        text-align: center;
    }
    .metric-value { font-size: 1.5rem; font-weight: 700; color: #1955AA; }
    .metric-label { font-size: 0.78rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; }
    
    /* Pricing Cards */
    .pricing-card {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 16px;
        padding: 2rem 1.5rem;
        text-align: center;
        position: relative;
        height: 100%;
    }
    .pricing-card.featured {
        border: 2px solid #1955AA;
        box-shadow: 0 8px 24px rgba(25, 85, 170, 0.15);
    }
    .pricing-badge {
        position: absolute;
        top: -12px;
        left: 50%;
        transform: translateX(-50%);
        background: #1955AA;
        color: white;
        padding: 4px 16px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .pricing-name { font-size: 1.1rem; font-weight: 600; color: #374151; margin-bottom: 0.5rem; }
    .pricing-price { font-size: 2.2rem; font-weight: 700; color: #111827; }
    .pricing-period { font-size: 0.85rem; color: #9CA3AF; }
    .pricing-features { text-align: left; margin: 1.5rem 0; }
    .pricing-features li { 
        list-style: none; padding: 0.3rem 0; font-size: 0.88rem; color: #4B5563;
    }
    .pricing-features li::before { content: "✓ "; color: #10B981; font-weight: 700; }
    .pricing-features li.disabled { color: #D1D5DB; }
    .pricing-features li.disabled::before { content: "— "; color: #D1D5DB; }
    
    /* Narrative */
    .narrative-box {
        background: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 1.25rem 1.5rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    .narrative-box p { margin-bottom: 0.75rem; line-height: 1.7; color: #1F2937; }
    
    /* Pro Upsell */
    .upsell-box {
        background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%);
        border: 1px solid #93C5FD;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin: 1.5rem 0;
    }
    
    /* Footer */
    .footer {
        background: #F9FAFB;
        border-top: 1px solid #E5E7EB;
        padding: 2rem;
        margin-top: 3rem;
        border-radius: 12px;
        text-align: center;
    }
    .footer p { color: #6B7280; font-size: 0.85rem; margin: 0.25rem 0; }
    .footer a { color: #1955AA; text-decoration: none; }
    
    /* Hide Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    
    /* Responsive */
    @media (max-width: 768px) {
        .hero-title { font-size: 1.8rem; }
        .hero-container { padding: 2rem 1.5rem; }
    }
</style>
""", unsafe_allow_html=True)


# ── Session State ──
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "pro_key" not in st.session_state:
    st.session_state.pro_key = None
if "page" not in st.session_state:
    st.session_state.page = "main"


def _is_pro() -> bool:
    return st.session_state.pro_key is not None and st.session_state.pro_key.strip() != ""


# ── Navigation ──
def set_page(page: str):
    st.session_state.page = page


# ═══════════════════════════════════════════════════════════════
# Functions (must be defined before page rendering)
# ═══════════════════════════════════════════════════════════════

def _run_analysis(uploaded_files, question, company_name):
    """Execute the full analysis pipeline."""
    t0 = time.time()
    progress = st.progress(0, text="Loading and detecting file formats...")

    try:
        from analyst.web_loader import load_multiple_files

        files = [(f, f.name) for f in uploaded_files]
        events, oee, descriptions = load_multiple_files(files)
        progress.progress(20, text=f"Parsed {len(events):,} events, {len(oee):,} OEE intervals")

        if not events and not oee:
            st.error(
                "⚠️ No parseable data found. Make sure your files have columns for "
                "timestamps, equipment/machine names, and duration."
            )
            return

        for desc in descriptions:
            st.toast(f"📊 {desc}", icon="✅")

        progress.progress(35, text="Computing equipment profiles, shift patterns, trends...")
        from analyst.engine import analyze
        result = analyze(events, oee)

        progress.progress(50, text="AI is writing the analysis narrative (~30-60s)...")
        from analyst.narrative import generate_narrative
        narrative = generate_narrative(result, question)

        fixes = []
        if _is_pro():
            progress.progress(70, text="Researching root causes and corrective actions (Pro)...")
            from analyst.researcher import research_fixes
            operational_names = {
                "unassigned", "not scheduled", "unknown", "short stop",
                "change over", "break-lunch", "breaks/lunch/meals",
                "breaks, lunch, meals", "break relief other line",
                "training - meeting", "meetings", "other", "holiday",
                "no stock", "bad stock", "drive off", "power outage",
            }
            real_equipment = [
                ep for ep in result.equipment_profiles
                if ep.equipment_raw_name.lower().strip() not in operational_names
                and ep.equipment_id is not None
            ]
            fixes = research_fixes(real_equipment[:3])

        progress.progress(85, text="Rendering PDF report...")
        from analyst.renderer import render_pdf_bytes
        pdf_bytes, pdf_filename = render_pdf_bytes(
            result, narrative, fixes,
            question=question, company_name=company_name,
        )

        elapsed = time.time() - t0
        progress.progress(100, text=f"✅ Complete in {elapsed:.1f}s")
        time.sleep(0.5)
        progress.empty()

        # Store in session
        st.session_state.analysis_done = True
        st.session_state.last_result = result
        st.session_state.last_narrative = narrative
        st.session_state.last_fixes = fixes
        st.session_state.last_pdf = pdf_bytes
        st.session_state.last_pdf_name = pdf_filename
        st.rerun()

    except ValueError as e:
        progress.empty()
        st.error(f"⚠️ {str(e)}")
    except Exception as e:
        progress.empty()
        st.error(f"❌ Analysis failed: {str(e)}")
        with st.expander("Technical details"):
            import traceback
            st.code(traceback.format_exc())


def _show_results():
    """Display analysis results."""
    result = st.session_state.last_result
    narrative = st.session_state.last_narrative
    fixes = st.session_state.last_fixes
    pdf_bytes = st.session_state.last_pdf
    pdf_filename = st.session_state.last_pdf_name

    st.markdown("---")
    st.markdown('<div class="section-header">📋 Analysis Results</div>', unsafe_allow_html=True)

    # Key metrics
    oee_str = f"{result.avg_oee:.1%}" if result.avg_oee else "N/A"
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-box">
            <div class="metric-value">{result.total_events:,}</div>
            <div class="metric-label">Total Events</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{result.total_downtime_hours:.0f}h</div>
            <div class="metric-label">Total Downtime</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{oee_str}</div>
            <div class="metric-label">Average OEE</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{result.top_loss_driver[:18]}</div>
            <div class="metric-label">Top Loss Driver</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Narrative
    res_left, res_right = st.columns([3, 2], gap="large")

    with res_left:
        st.markdown("#### The Analysis")
        verdict_html = narrative.verdict.replace('\n', '<br/>')
        paras_html = ''.join(f'<p>{p}</p>' for p in narrative.evidence_paragraphs if p.strip())
        st.markdown(f"""
        <div class="narrative-box">
            <p><strong>{verdict_html}</strong></p>
            {paras_html}
        </div>
        """, unsafe_allow_html=True)

        # Download
        st.download_button(
            label=f"📥  Download Full PDF Report",
            data=pdf_bytes,
            file_name=pdf_filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

        # Pro upsell
        if not _is_pro() and not fixes:
            st.markdown("""
            <div class="upsell-box">
                <strong>🔓 Unlock Root Cause Analysis</strong><br/>
                <span style="color: #4B5563;">
                Pro reports include specific root causes for your top 3 equipment issues, 
                corrective actions your maintenance team can execute today, PM schedule additions, 
                and memory that tracks whether your fixes are working.
                </span>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Upgrade to Pro →", type="primary", key="upsell_btn"):
                set_page("get_pro")
                st.rerun()

    with res_right:
        st.markdown("#### Equipment Breakdown")
        if result.equipment_profiles:
            import pandas as pd
            equip_data = []
            for ep in result.equipment_profiles[:12]:
                equip_data.append({
                    "Equipment": ep.equipment_raw_name[:25],
                    "Events": ep.event_count,
                    "Hours": round(ep.total_downtime_hours, 1),
                    "MTBF": f"{ep.mtbf_minutes:.0f}m" if ep.mtbf_minutes else "—",
                    "Repeat": f"{ep.repeat_failure_rate:.0%}",
                })
            st.dataframe(
                pd.DataFrame(equip_data),
                use_container_width=True,
                hide_index=True,
                height=min(len(equip_data) * 38 + 40, 500),
            )

        st.markdown("#### Shift Comparison")
        if result.shift_profiles:
            import pandas as pd
            shift_data = []
            for sp in result.shift_profiles:
                shift_data.append({
                    "Shift": sp.shift,
                    "OEE": f"{sp.avg_oee:.1%}" if sp.avg_oee else "N/A",
                    "Events": sp.event_count,
                    "Downtime": f"{sp.total_downtime_hours:.0f}h",
                    "Unassigned": f"{sp.unassigned_rate:.1%}",
                    "Avg Recovery": f"{sp.avg_recovery_minutes:.1f}m",
                })
            st.dataframe(
                pd.DataFrame(shift_data),
                use_container_width=True,
                hide_index=True,
            )


def _get_pro_page():
    """Pro access / payment page."""
    if st.button("← Back to Analyzer", key="back_from_pro"):
        set_page("main")
        st.rerun()

    st.markdown("---")
    st.markdown('<div class="section-header">Get Pro Access</div>', unsafe_allow_html=True)

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown("""
        ### What you get with Pro
        
        **Root Cause Analysis** — For your top 3 equipment loss drivers, get:
        - What the failure mode means mechanically
        - Probable root causes ranked by likelihood
        - Specific corrective actions (not generic "improve maintenance")
        - PM schedule additions your team can implement today
        
        **Memory Across Uploads** — Upload data monthly and track:
        - Is OEE improving or worsening?
        - Are the same equipment still your top losses?
        - Did the recommended fix actually work?
        
        **Company Branding** — Your company name on every report PDF
        
        **Unlimited Reports** — No monthly cap
        
        **Email Support** — Direct line to a real manufacturing engineer
        """)

        st.markdown("---")
        st.markdown("#### ROI Calculator")
        downtime_cost = st.number_input(
            "What does 1 hour of unplanned downtime cost you?",
            min_value=100, max_value=1000000, value=5000, step=500,
            format="%d",
        )
        hours_saved = st.slider("Hours of downtime the first fix could save per month", 1, 50, 4)
        monthly_savings = downtime_cost * hours_saved
        st.markdown(
            f"**Potential monthly savings: ${monthly_savings:,.0f}**  \n"
            f"Pro costs $149/mo → **{monthly_savings / 149:.0f}x ROI**"
        )

    with right:
        st.markdown("### Start Your Pro Subscription")
        st.markdown("")

        with st.form("pro_signup", clear_on_submit=False):
            name = st.text_input("Full Name *")
            email = st.text_input("Work Email *")
            company = st.text_input("Company")
            plant_count = st.selectbox("Number of production lines", ["1-3", "4-10", "11-25", "25+"])
            mes_system = st.selectbox(
                "Current MES / data system",
                ["Traksys", "SAP", "Ignition", "Excel / Manual", "Other", "Not sure"],
            )
            comments = st.text_area("Anything else we should know?", height=80)

            submitted = st.form_submit_button("Request Pro Access", type="primary", use_container_width=True)

            if submitted:
                if not name or not email:
                    st.error("Please fill in your name and email.")
                elif "@" not in email:
                    st.error("Please enter a valid email address.")
                else:
                    _save_lead("pro", name, email, company, plant_count, mes_system, comments)
                    st.success(
                        "✅ **Request received!** We'll send your Pro key within 24 hours. "
                        "Check your email for next steps."
                    )
                    st.balloons()

        st.markdown("""
        <div style="background: #F9FAFB; border-radius: 8px; padding: 1rem; margin-top: 1rem; font-size: 0.85rem; color: #6B7280;">
            <strong>What happens next:</strong><br/>
            1. We'll verify your info and set up your account<br/>
            2. You'll receive a Pro key via email<br/>
            3. Enter the key in the sidebar to unlock Pro features<br/>
            4. Start generating full root-cause reports immediately
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #9CA3AF;">
            30-day money-back guarantee. Cancel anytime.<br/>
            Questions? <a href="mailto:brian@crusoeanalytics.com">brian@crusoeanalytics.com</a>
        </div>
        """, unsafe_allow_html=True)


def _contact_page():
    """Enterprise contact page."""
    if st.button("← Back to Analyzer", key="back_from_contact"):
        set_page("main")
        st.rerun()

    st.markdown("---")
    st.markdown('<div class="section-header">Enterprise Inquiry</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subheader">'
        'For multi-plant operations that need API access, custom integrations, and dedicated support.'
        '</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown("""
        ### Enterprise includes everything in Pro, plus:
        
        **API Access**  
        `POST /analyze` with your file, `GET /report/{id}` for the result. 
        Integrate directly into your MES export pipeline or scheduling system.
        
        **Multi-Line Comparison**  
        One report that compares all your lines side by side — OEE, downtime patterns, 
        crew performance. See which line needs attention and which is a model.
        
        **Custom Equipment Dictionaries**  
        Map your equipment names to standard categories. "CASE-PKR-L3-NORTH" becomes 
        "Case Packer" automatically. Works with your naming conventions, not ours.
        
        **Custom Shift Definitions**  
        12-hour shifts? Rotating schedules? Continental pattern? We configure it to match your plant.
        
        **Webhook Delivery**  
        Reports auto-delivered to email, Microsoft Teams, or Slack when your MES export lands.
        
        **Onboarding Call**  
        30-minute call with a manufacturing engineer to configure the system for your operation. 
        Not a sales rep — someone who's actually run a production floor.
        
        **Priority Support**  
        Direct email and response within 4 business hours.
        """)

    with right:
        st.markdown("### Tell Us About Your Operation")
        st.markdown("")

        with st.form("enterprise_contact", clear_on_submit=False):
            name = st.text_input("Full Name *")
            email = st.text_input("Work Email *")
            company = st.text_input("Company *")
            title = st.text_input("Your Title")
            plant_count = st.selectbox("Number of plants", ["1", "2-5", "6-10", "10+"])
            lines_per_plant = st.selectbox("Lines per plant (avg)", ["1-3", "4-10", "11-25", "25+"])
            mes_system = st.selectbox(
                "Current MES system",
                ["Traksys", "SAP", "Siemens OpCenter", "Ignition", "Wonderware", "Excel / Manual", "Other"],
            )
            industry = st.selectbox(
                "Industry",
                ["Food & Beverage", "Pharmaceutical", "Automotive", "Electronics", "Consumer Goods", "Chemical", "Other"],
            )
            use_case = st.text_area(
                "What problem are you trying to solve?",
                height=100,
                placeholder="e.g., We have 8 canning lines and can't figure out why Line 3 underperforms...",
            )

            submitted = st.form_submit_button("Request Enterprise Demo", type="primary", use_container_width=True)

            if submitted:
                if not name or not email or not company:
                    st.error("Please fill in name, email, and company.")
                elif "@" not in email:
                    st.error("Please enter a valid email address.")
                else:
                    _save_lead(
                        "enterprise", name, email, company,
                        f"{plant_count} plants, {lines_per_plant} lines/plant",
                        mes_system, f"Title: {title}\nIndustry: {industry}\nUse case: {use_case}",
                    )
                    st.success(
                        "✅ **Inquiry received!** We'll reach out within 1 business day "
                        "to schedule your demo and onboarding call."
                    )
                    st.balloons()

        st.markdown("""
        <div style="text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #9CA3AF;">
            Prefer to talk first? Email <a href="mailto:brian@crusoeanalytics.com">brian@crusoeanalytics.com</a>
            <br/>or call directly.
        </div>
        """, unsafe_allow_html=True)


def _save_lead(tier: str, name: str, email: str, company: str, details: str, mes: str, comments: str):
    """Save lead info."""
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    lead = {
        "tier": tier,
        "name": name,
        "email": email,
        "company": company,
        "details": details,
        "mes_system": mes,
        "comments": comments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    leads_dir = Path("leads")
    leads_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    (leads_dir / f"lead_{tier}_{ts}.json").write_text(json.dumps(lead, indent=2))


# ═══════════════════════════════════════════════════════════════
# Page Rendering (all functions defined above)
# ═══════════════════════════════════════════════════════════════

# ── HERO SECTION ──
st.markdown("""
<div class="hero-container">
    <div class="hero-title">The engineer who reads<br/>your production data.</div>
    <div class="hero-subtitle">
        Upload your MES exports or downtime logs. Get an intelligent analysis report 
        that names specific equipment, specific shifts, and tells you exactly what to fix first.
        In under 3 minutes. No software to install. No data stored.
    </div>
    <div>
        <span class="hero-stat">
            <span class="hero-stat-number">$11B</span><br/>
            <span class="hero-stat-label">Manufacturing Analytics Market</span>
        </span>
        <span class="hero-stat">
            <span class="hero-stat-number">92%</span><br/>
            <span class="hero-stat-label">Say tech investments underdeliver</span>
        </span>
        <span class="hero-stat">
            <span class="hero-stat-number">&lt;3 min</span><br/>
            <span class="hero-stat-label">From upload to insight</span>
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Privacy strip
st.markdown("""
<div class="privacy-strip">
    🔒 <strong>Zero data retention.</strong> Your files are processed in memory and immediately discarded. 
    Nothing is stored, logged, or shared. We never see your data.
</div>
""", unsafe_allow_html=True)


# ── MAIN PAGE ──
if st.session_state.page == "main":

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.markdown("---")

        st.markdown("### 🔑 Pro Access")
        pro_input = st.text_input(
            "Pro Key",
            type="password",
            value=st.session_state.pro_key or "",
            help="Enter your Pro key to unlock root cause analysis, fixes, and memory",
        )
        if pro_input != (st.session_state.pro_key or ""):
            st.session_state.pro_key = pro_input if pro_input.strip() else None
            st.rerun()

        if _is_pro():
            st.success("✅ Pro features active")
        else:
            st.caption("No key? [Get Pro access](#pricing)")

        st.markdown("---")
        question = st.text_area(
            "Analysis question",
            value="What is costing this line the most production, and what should we fix first?",
            height=80,
        )

        company_name = None
        if _is_pro():
            company_name = st.text_input("Company name (for PDF header)")

        st.markdown("---")
        st.markdown("### Supported Formats")
        st.caption("""
        • Traksys MES exports (auto-detected)
        • Generic CSV/Excel with columns: date, equipment, duration
        • Upload event + OEE files together for richer analysis
        """)

    # ── Upload + Analysis Section ──
    left_col, right_col = st.columns([3, 2], gap="large")

    with left_col:
        st.markdown('<div class="section-header">Upload Your Data</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-subheader">Drag and drop your MES exports, downtime logs, or OEE reports.</div>',
            unsafe_allow_html=True,
        )

        uploaded_files = st.file_uploader(
            "Drop files here",
            type=["xlsx", "xls", "csv", "tsv"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded_files:
            for f in uploaded_files:
                st.caption(f"📄 **{f.name}** — {f.size / 1024:.0f} KB")

            analyze_btn = st.button("🔍  Analyze My Data", type="primary", use_container_width=True)

            if analyze_btn:
                _run_analysis(uploaded_files, question, company_name)

    with right_col:
        if not uploaded_files and not st.session_state.analysis_done:
            st.markdown('<div class="section-header">How It Works</div>', unsafe_allow_html=True)

            st.markdown("""
            <div class="feature-card" style="margin-bottom: 1rem;">
                <h4>📤 1. Upload</h4>
                <p>Drop your Excel or CSV files — downtime logs, MES event exports, OEE reports. 
                We auto-detect the format.</p>
            </div>
            <div class="feature-card" style="margin-bottom: 1rem;">
                <h4>⚡ 2. AI Analysis</h4>
                <p>Our engine computes equipment MTBF, repeat failure rates, shift patterns, 
                and cross-shift comparisons. Then AI writes the narrative — like a senior plant engineer.</p>
            </div>
            <div class="feature-card" style="margin-bottom: 1rem;">
                <h4>📄 3. Download Report</h4>
                <p>Get a PDF that names specific equipment, specific shifts, and one clear recommendation. 
                The kind of report that makes a plant manager say "how did it know that?"</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div class="feature-card" style="border-color: #1955AA; border-width: 2px;">
                <h4>🛡️ Not Another Dashboard</h4>
                <p>Every OEE tool shows numbers. This one <strong>reads</strong> numbers and tells you what they mean. 
                Written in prose, not bullet points. Answers, not charts.</p>
            </div>
            """, unsafe_allow_html=True)

    # ── Results Section (if analysis is done) ──
    if st.session_state.analysis_done and hasattr(st.session_state, 'last_result'):
        _show_results()

    # ── Pricing Section ──
    st.markdown("---")
    st.markdown('<a id="pricing"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-header" style="text-align:center;">Simple, Transparent Pricing</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subheader" style="text-align:center;">'
        'Start free. Upgrade when you need root causes and fixes.</div>',
        unsafe_allow_html=True,
    )

    p1, p2, p3 = st.columns(3, gap="medium")

    with p1:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-name">Starter</div>
            <div class="pricing-price">$0</div>
            <div class="pricing-period">forever</div>
            <ul class="pricing-features">
                <li>Narrative analysis report</li>
                <li>Equipment breakdown table</li>
                <li>Shift comparison</li>
                <li>PDF download</li>
                <li>3 reports per month</li>
                <li class="disabled">Root cause analysis</li>
                <li class="disabled">Corrective actions & PM adds</li>
                <li class="disabled">Memory across uploads</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with p2:
        st.markdown("""
        <div class="pricing-card featured">
            <div class="pricing-badge">Most Popular</div>
            <div class="pricing-name">Pro</div>
            <div class="pricing-price">$149</div>
            <div class="pricing-period">per month</div>
            <ul class="pricing-features">
                <li>Everything in Starter</li>
                <li>Root cause analysis (top 3 equipment)</li>
                <li>Specific corrective actions</li>
                <li>PM schedule additions</li>
                <li>Memory across uploads</li>
                <li>Company branding on reports</li>
                <li>Unlimited reports</li>
                <li>Email support</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Get Pro Access →", type="primary", use_container_width=True, key="pro_btn"):
            set_page("get_pro")
            st.rerun()

    with p3:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-name">Enterprise</div>
            <div class="pricing-price">$499</div>
            <div class="pricing-period">per month</div>
            <ul class="pricing-features">
                <li>Everything in Pro</li>
                <li>API access</li>
                <li>Multi-line comparison reports</li>
                <li>Custom equipment dictionaries</li>
                <li>Custom shift definitions</li>
                <li>Webhook delivery (email/Teams/Slack)</li>
                <li>Priority support from a real engineer</li>
                <li>Onboarding call</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Contact Us →", use_container_width=True, key="enterprise_btn"):
            set_page("contact")
            st.rerun()

    # ── Credibility Section ──
    st.markdown("---")
    st.markdown('<div class="section-header" style="text-align:center;">Built By Someone Who\'s Run the Lines</div>', unsafe_allow_html=True)

    cr1, cr2, cr3 = st.columns(3, gap="medium")
    with cr1:
        st.markdown("""
        <div class="feature-card" style="text-align:center;">
            <h4>🏭 8+ Years</h4>
            <p>Production supervision and management across 4 food manufacturing plants. 
            Canning, chicken, baked goods, frozen.</p>
        </div>
        """, unsafe_allow_html=True)
    with cr2:
        st.markdown("""
        <div class="feature-card" style="text-align:center;">
            <h4>📊 Six Sigma BB</h4>
            <p>Black Belt certified. Led teams of up to 170 people. 
            Managed OEE, downtime, quality, and continuous improvement.</p>
        </div>
        """, unsafe_allow_html=True)
    with cr3:
        st.markdown("""
        <div class="feature-card" style="text-align:center;">
            <h4>💻 MES / Traksys</h4>
            <p>Deep experience with Traksys MES, production scheduling, 
            and turning messy floor data into actionable intelligence.</p>
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ──
    st.markdown("""
    <div class="footer">
        <p><strong>Manufacturing Analyst Pro</strong> — The engineer who reads your data.</p>
        <p>🔒 Your data is processed in memory and immediately discarded. Nothing stored. Ever.</p>
        <p style="margin-top: 0.75rem;">
            <a href="#pricing">Pricing</a> · 
            <a href="mailto:brian@crusoeanalytics.com">Contact</a> · 
            <a href="https://linkedin.com/in/brian-crusoe" target="_blank">LinkedIn</a>
        </p>
        <p style="color: #9CA3AF; font-size: 0.75rem; margin-top: 0.75rem;">
            © 2026 Crusoe Analytics. All rights reserved.
        </p>
    </div>
    """, unsafe_allow_html=True)


# ── GET PRO PAGE ──
elif st.session_state.page == "get_pro":
    _get_pro_page()


# ── CONTACT PAGE ──
elif st.session_state.page == "contact":
    _contact_page()


