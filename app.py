"""Spreadshop — Skroutz Market Analysis Tool for Resellers."""
from __future__ import annotations

import datetime
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import streamlit as st

from logger import setup_logging
from parsers.base import ParseError, ProductRecord, SkroutzResult, parse_file
from scraper.cache import ScrapeCache
from scraper import get_scraper
from analysis.compare import ProductAnalysis, analyze
from analysis.export import generate_xlsx
from config import HEADLESS_MODE, SCRAPER_DEFAULT_DELAY, SCRAPER_CONCURRENCY, SCRAPER_SOURCE, SERPAPI_KEY, ESHOP_PORT, ESHOP_OUTPUT_DIR
import scrape_buffer as _SB
import eshop_buffer as _EB

setup_logging()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Spreadshop",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* DESIGN TOKENS */
:root {
    --bg:             #0B0E14;
    --surface:        #0E1217;
    --surface-raised: #13181F;
    --surface-deep:   #080B0F;
    --border:         #1F242C;
    --border-subtle:  #191D24;
    --accent:         #10B981;
    --accent-dim:     #052E1C;
    --accent-mid:     #0A7A55;
    --accent-text:    #34D399;
    --danger:         #EF4444;
    --danger-dim:     #2D0A0A;
    --warn:           #F59E0B;
    --warn-dim:       #2A1700;
    --text-primary:   #E6EDF3;
    --text-secondary: #7D8590;
    --text-muted:     #4A5160;
}

/* BASE */
html, body, .stApp {
    font-family: 'Inter Tight', system-ui, -apple-system, sans-serif !important;
}
.stApp {
    background-color: var(--bg) !important;
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

/* TYPOGRAPHY */
h3 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    margin-bottom: 4px !important;
}
h4 {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
    color: var(--text-secondary) !important;
    margin: 24px 0 14px 0 !important;
}
h5 {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--text-secondary) !important;
    margin: 20px 0 10px 0 !important;
}
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 20px 0 !important;
}

/* METRIC CARDS */
[data-testid="metric-container"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 18px 22px;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-feature-settings: "tnum" !important;
    font-size: 1.6rem !important;
    font-weight: 500;
    color: var(--text-primary);
    letter-spacing: -0.01em;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: var(--text-secondary);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* PRIMARY BUTTON */
[data-testid="stBaseButton-primary"] {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    height: 44px !important;
    border-radius: 4px !important;
    letter-spacing: 0.01em !important;
    transition: opacity 0.12s !important;
}
[data-testid="stBaseButton-primary"]:hover {
    opacity: 0.88 !important;
}
[data-testid="stBaseButton-primary"]:focus-visible,
[data-testid="stBaseButton-secondary"]:focus-visible,
[data-testid="stBaseButton-borderless"]:focus-visible {
    outline: 2px solid var(--accent) !important;
    outline-offset: 2px !important;
}

/* HERO METRIC STRIP */
.hero-metric-strip {
    padding: 16px 0 20px 0;
    margin-bottom: 16px;
}
.hm-label {
    font-size: 0.63rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 8px;
}
.hm-value {
    font-size: 2.8rem; font-weight: 500; color: var(--accent);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -0.02em;
    line-height: 1; margin-bottom: 8px; font-feature-settings: "tnum";
}
.hm-rule { width: 24px; height: 1px; background: var(--border); margin: 10px 0 8px 0; }
.hm-sub { font-size: 0.78rem; color: var(--text-secondary); }

/* INVEST ROW */
.invest-row {
    font-size: 0.82rem; color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-feature-settings: "tnum";
    padding: 12px 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    margin: 4px 0 20px 0;
}
.invest-row strong { color: var(--text-primary); }
.invest-row .ir-accent { color: var(--accent-text); font-weight: 600; }

/* STAT STRIP */
.stat-strip {
    font-size: 0.8rem; color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-feature-settings: "tnum";
    padding: 10px 0 16px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
}
.stat-strip strong { color: var(--text-primary); }
.stat-strip .stat-sep { color: var(--border); margin: 0 12px; }
.stat-strip .stat-accent { color: var(--accent-text); font-weight: 600; }

/* OPP CARDS */
.opp-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 16px 18px; height: 100%;
}
.opp-card.strong-buy { border-left: 2px solid var(--accent); }
.opp-card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px;
}
.opp-card-title {
    font-size: 0.83rem; color: var(--text-primary); font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px;
}
.opp-card-sub { font-size: 0.71rem; color: var(--text-muted); margin-top: 3px; }
.opp-margin-bar { height: 1px; background: var(--border); margin: 8px 0; overflow: hidden; }
.opp-margin-fill { height: 100%; background: var(--accent); }
.opp-card-metrics { display: flex; gap: 16px; margin-top: 10px; }
.opp-card-metrics .m-label { font-size: 0.63rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px; }
.opp-card-metrics .m-value { font-size: 0.88rem; font-weight: 500; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; font-feature-settings: "tnum"; }
.opp-card-metrics .m-value.green { color: var(--accent-text); }
.opp-card-metrics .m-value.amber { color: var(--warn); }
.opp-card-metrics .m-value.red   { color: var(--danger); }

/* BADGES */
.badge-strong   { background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 2px; font-size: 0.68rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.05em; text-transform: uppercase; white-space: nowrap; }
.badge-consider { color: var(--text-secondary); padding: 2px 8px; border-radius: 2px; font-size: 0.68rem; font-weight: 600; border: 1px solid var(--border); white-space: nowrap; }
.badge-skip     { color: var(--text-muted); padding: 2px 8px; border-radius: 2px; font-size: 0.68rem; font-weight: 600; border: 1px solid var(--border-subtle); white-space: nowrap; }
.badge-nf       { color: var(--text-muted); padding: 2px 8px; border-radius: 2px; font-size: 0.68rem; font-weight: 600; border: 1px solid var(--border-subtle); white-space: nowrap; }

/* SUPPLIER CARDS */
.supplier-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 12px 18px;
    display: flex; align-items: center; gap: 14px; margin-bottom: 6px;
}
.sc-type { font-size: 0.63rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); background: var(--bg); border: 1px solid var(--border); border-radius: 2px; padding: 2px 7px; flex-shrink: 0; font-family: 'JetBrains Mono', monospace; }
.sc-name { font-size: 0.86rem; color: var(--text-primary); font-weight: 600; }
.sc-meta { font-size: 0.71rem; color: var(--text-muted); margin-top: 2px; }
.sc-badge { margin-left: auto; font-size: 0.68rem; padding: 2px 8px; border-radius: 2px; white-space: nowrap; flex-shrink: 0; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 0.05em; }
.sc-badge-ok   { background: var(--accent-dim);  color: var(--accent-text); border: 1px solid var(--accent-mid); }
.sc-badge-warn { background: var(--warn-dim);     color: var(--warn);        border: 1px solid #7A4E0040; }
.sc-badge-err  { background: var(--danger-dim);   color: var(--danger);      border: 1px solid #7A000040; }

/* EMPTY STATES */
.empty-state { padding: 60px 0 40px 0; color: var(--text-muted); }
.es-title { font-size: 0.88rem; color: var(--text-secondary); font-weight: 600; margin-bottom: 8px; }
.es-hint  { font-size: 0.8rem; line-height: 1.7; color: var(--text-muted); }
.es-hint strong { color: var(--text-secondary); }

/* SCRAPE LOG */
.scrape-log {
    background: var(--surface-deep); border: 1px solid var(--border);
    border-radius: 4px; padding: 12px 14px; font-size: 0.76rem;
    color: var(--text-secondary); max-height: 220px; overflow-y: auto;
    font-family: 'JetBrains Mono', monospace; line-height: 1.65;
}

/* LANDING PAGE */
.landing-hero {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    text-align: center;
    padding: 72px 24px 56px;
    min-height: 64vh;
}
.landing-wordmark {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 36px; display: inline-block;
}
.landing-headline {
    font-size: clamp(2.2rem, 4.5vw, 3.2rem);
    font-weight: 700; line-height: 1.1;
    color: var(--text-primary);
    letter-spacing: -0.03em;
    margin-bottom: 20px;
}
.landing-headline em { color: var(--accent-text); font-style: normal; }
.landing-sub {
    font-size: 1.0rem; color: var(--text-secondary);
    max-width: 480px; line-height: 1.75; margin-bottom: 40px;
}
.landing-trust-strip {
    margin-top: 40px; padding-top: 20px;
    border-top: 1px solid var(--border);
}
.trust-line {
    font-size: 0.68rem; color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.06em; text-transform: uppercase;
}

/* HOW IT WORKS */
.how-section { padding: 16px 0 40px 0; }
.how-step {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 24px 22px; height: 100%;
}
.hs-num {
    font-size: 0.68rem; font-weight: 700; color: var(--accent);
    letter-spacing: 0.08em; font-family: 'JetBrains Mono', monospace; margin-bottom: 10px;
}
.hs-label { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.hs-text { font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; }

/* WIZARD NAV */
.wn-brand {
    font-size: 0.82rem; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace; display: inline-block;
}
.step-nav { display: flex; gap: 0; align-items: center; justify-content: center; }
.step-tab {
    font-size: 0.72rem; font-weight: 500; color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace; letter-spacing: 0.03em;
    padding: 6px 14px 8px 14px;
    border-bottom: 2px solid transparent;
    cursor: default; white-space: nowrap;
}
.step-tab.done { color: var(--text-secondary); }
.step-tab.active {
    color: var(--text-primary);
    border-bottom-color: var(--accent);
    font-weight: 600;
}

/* STEP SCREENS */
.step-heading {
    font-size: 1.6rem; font-weight: 700; color: var(--text-primary);
    letter-spacing: -0.02em; margin-bottom: 10px; line-height: 1.15;
}
.step-sub {
    font-size: 0.92rem; color: var(--text-secondary);
    line-height: 1.7; margin-bottom: 28px;
}

/* E-SHOP RUNNING ROW */
.eshop-running-row {
    font-size: 0.82rem; color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    padding: 14px 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
    display: flex; align-items: center; gap: 10px;
}
.eshop-running-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent); flex-shrink: 0;
    animation: pulse-dot 1.8s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
.eshop-running-row a { color: var(--accent); text-decoration: none; }
.eshop-running-row a:hover { text-decoration: underline; }

/* Results mode toggle */
[data-testid="stToggle"] label {
    font-size: 0.75rem !important;
    font-family: 'JetBrains Mono', monospace !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "products":       [],
        "parse_errors":   [],
        "parse_summary":  [],
        "skroutz_results": {},
        "analyses":       [],
        "scrape_paused":  False,
        "last_scraped_at": None,
        "advanced_mode":  False,
        # E-shop screen
        "eshop_url":         None,    # "http://localhost:NNNN" when server is running
        "eshop_output_dir":  None,    # Path of last generated site
        "eshop_store_name":  "",      # store name entered by user
        "eshop_color":       "green", # selected color scheme key
        "eshop_template":    "t1",   # selected template: t1, t2, or t3
        "eshop_tagline":     "",      # short tagline shown in footer
        "eshop_headline":    "",      # hero headline
        "eshop_subheadline": "",      # hero supporting text
        "eshop_logo_bytes":  None,    # raw bytes of uploaded logo file
        "eshop_logo_ext":    "png",   # file extension of uploaded logo
        "eshop_font":        "modern",# font pairing key
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Screen routing — set once on first page load
    if "screen" not in st.session_state:
        if st.session_state.get("analyses"):
            st.session_state["screen"] = "results"
        elif st.session_state.get("products"):
            st.session_state["screen"] = "fetch"
        else:
            st.session_state["screen"] = "landing"


_init_state()

# ---------------------------------------------------------------------------
# Background scrape sync — must run on every render (before routing)
# ---------------------------------------------------------------------------
if _SB.analyses_ready:
    st.session_state["skroutz_results"] = dict(_SB.results)
    st.session_state["last_scraped_at"] = _SB.scraped_at
    st.session_state["analyses"] = analyze(
        st.session_state["products"],
        st.session_state["skroutz_results"],
    )
    _SB.analyses_ready = False
    st.session_state["screen"] = "results"
    st.rerun()


# ---------------------------------------------------------------------------
# Navigation helper
# ---------------------------------------------------------------------------
def _go(screen: str) -> None:
    st.session_state["screen"] = screen
    st.rerun()


# ---------------------------------------------------------------------------
# Wizard nav bar  (used on upload / fetch / results screens)
# ---------------------------------------------------------------------------
def _render_wizard_nav(step: int) -> None:
    step_labels = ["Load Catalog", "Fetch Prices", "Your Results", "Build E-Shop"]

    tabs_html = "".join(
        f'<span class="step-tab {("active" if i + 1 == step else "done" if i + 1 < step else "")}">'
        f'{str(i + 1).zfill(2)}&nbsp;{label}</span>'
        for i, label in enumerate(step_labels)
    )

    col_l, col_c, col_r = st.columns([1, 3, 1])

    with col_l:
        st.markdown('<div class="wn-brand">Spreadshop</div>', unsafe_allow_html=True)

    with col_c:
        st.markdown(f'<div class="step-nav">{tabs_html}</div>', unsafe_allow_html=True)

    with col_r:
        if step == 3:
            if st.button("Start Over", use_container_width=True):
                for key in ("products", "parse_errors", "parse_summary", "analyses"):
                    st.session_state[key] = []
                st.session_state["skroutz_results"] = {}
                st.session_state["last_scraped_at"] = None
                _go("landing")
        elif step == 4:
            if st.button("← Results", use_container_width=True):
                _go("results")
        elif step in (1, 2):
            back_screen = "landing" if step == 1 else "upload"
            if st.button("← Back", use_container_width=True):
                _go(back_screen)

    st.markdown('<hr style="margin:8px 0 32px 0">', unsafe_allow_html=True)


# ===========================================================================
# SCREEN: LANDING
# ===========================================================================
def _render_landing() -> None:
    ss = st.session_state
    has_results = bool(ss.get("analyses"))
    has_catalog = bool(ss.get("products"))

    # Hero copy
    st.markdown("""
    <div class="landing-hero">
      <div class="landing-wordmark">Spreadshop &nbsp;&middot;&nbsp; GR Market Intelligence</div>
      <div class="landing-headline">Find the profit hiding in<br>your supplier&rsquo;s <em>catalog</em>.</div>
      <div class="landing-sub">
        Upload a wholesale price list. We match every product against live
        Skroutz.gr prices and show exactly what to stock &mdash; ranked by
        margin, competition, and demand.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # CTA buttons — centered using columns
    _, col_cta, _ = st.columns([2, 1.5, 2])
    with col_cta:
        if st.button("Get Started →", type="primary", use_container_width=True):
            _go("upload")
        if has_results:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("View Last Results →", use_container_width=True):
                _go("results")
        elif has_catalog:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Continue — Fetch Prices →", use_container_width=True):
                _go("fetch")

    # Trust strip
    st.markdown("""
    <div class="landing-trust-strip">
      <div class="trust-line">Live Skroutz.gr &nbsp;&middot;&nbsp; XLSX &amp; PDF &nbsp;&middot;&nbsp; Greek Market &nbsp;&middot;&nbsp; Export XLSX</div>
    </div>
    """, unsafe_allow_html=True)

    # How it works
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("#### How It Works", unsafe_allow_html=False)
    c1, c2, c3 = st.columns(3)
    c1.markdown("""
    <div class="how-step">
      <div class="hs-num">01</div>
      <div class="hs-label">Load Catalog</div>
      <div class="hs-text">Upload your supplier&rsquo;s XLSX or PDF price list. The app reads every product name, barcode, and wholesale price automatically.</div>
    </div>
    """, unsafe_allow_html=True)
    c2.markdown("""
    <div class="how-step">
      <div class="hs-num">02</div>
      <div class="hs-label">Fetch Prices</div>
      <div class="hs-text">We search Skroutz.gr for every product and pull the current selling price, number of competing shops, and demand signals.</div>
    </div>
    """, unsafe_allow_html=True)
    c3.markdown("""
    <div class="how-step">
      <div class="hs-num">03</div>
      <div class="hs-label">Buy Smarter</div>
      <div class="hs-text">Every product is ranked by profit potential. You see exactly what to stock, at what price, and what gross margin to expect.</div>
    </div>
    """, unsafe_allow_html=True)


# ===========================================================================
# SCREEN: UPLOAD  (Step 1)
# ===========================================================================
def _render_upload() -> None:
    _render_wizard_nav(1)

    _, col, _ = st.columns([1, 4, 1])
    with col:
        st.markdown('<div class="step-heading">Load Your Catalog</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="step-sub">Drop your supplier&rsquo;s price list below. '
            'We&rsquo;ll read every product and wholesale price automatically. '
            'Supports <strong style="color:var(--text-primary)">XLSX</strong> and '
            '<strong style="color:var(--text-primary)">PDF</strong> formats.</div>',
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Drop files here",
            type=["xlsx", "pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded:
            products: list[ProductRecord] = []
            errors:   list[ParseError]    = []
            summary:  list[dict]          = []
            ui_warnings: list[str]        = []

            tmp_dir = Path("cache/uploads")
            tmp_dir.mkdir(parents=True, exist_ok=True)

            for f in uploaded:
                tmp_path = tmp_dir / f.name
                tmp_path.write_bytes(f.read())
                try:
                    ps, es, ws = parse_file(tmp_path)
                    products.extend(ps)
                    errors.extend(es)
                    ui_warnings.extend(ws)
                    supplier = ps[0].source.title() if ps else "Unknown"
                    summary.append({
                        "File": f.name, "Supplier": supplier,
                        "Type": f.name.rsplit(".", 1)[-1].upper(),
                        "Products": len(ps), "Parse Errors": len(es),
                        "Status": "OK" if not es else f"{len(es)} warning(s)",
                    })
                except Exception as exc:
                    summary.append({
                        "File": f.name, "Supplier": "—", "Type": "—",
                        "Products": 0, "Parse Errors": 1, "Status": f"Error: {exc}",
                    })

            for w in ui_warnings:
                st.warning(w)

            st.markdown(f"**{len(products)} products** loaded from **{len(uploaded)} file(s)**")

            for row in summary:
                _bc = ("sc-badge-ok" if row["Parse Errors"] == 0
                       else ("sc-badge-err" if "Error" in row["Status"] else "sc-badge-warn"))
                st.markdown(f"""
                <div class="supplier-card">
                  <span class="sc-type">{row["Type"]}</span>
                  <div>
                    <div class="sc-name">{row["Supplier"]}</div>
                    <div class="sc-meta">{row["File"]} &middot; {row["Products"]} products</div>
                  </div>
                  <span class="sc-badge {_bc}">{row["Status"]}</span>
                </div>
                """, unsafe_allow_html=True)

            if errors:
                with st.expander(f"{len(errors)} parse warning(s)"):
                    st.dataframe(
                        [{"File": e.filename, "Row": e.row, "Reason": e.reason, "Raw": e.raw or ""}
                         for e in errors],
                        use_container_width=True, hide_index=True,
                    )

            if products:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Confirm & Continue →", type="primary", use_container_width=True):
                    st.session_state["products"]      = products
                    st.session_state["parse_errors"]  = errors
                    st.session_state["parse_summary"] = summary
                    st.session_state["analyses"]      = []
                    _go("fetch")

        elif st.session_state["products"]:
            n = len(st.session_state["products"])
            st.info(f"**{n} products** already loaded. Upload new files to replace them, or continue.")
            for row in st.session_state.get("parse_summary", []):
                _bc = ("sc-badge-ok" if row["Parse Errors"] == 0
                       else ("sc-badge-err" if "Error" in row["Status"] else "sc-badge-warn"))
                st.markdown(f"""
                <div class="supplier-card">
                  <span class="sc-type">{row["Type"]}</span>
                  <div>
                    <div class="sc-name">{row["Supplier"]}</div>
                    <div class="sc-meta">{row["File"]} &middot; {row["Products"]} products</div>
                  </div>
                  <span class="sc-badge {_bc}">{row["Status"]}</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Continue with Loaded Catalog →", type="primary", use_container_width=True):
                _go("fetch")


# ===========================================================================
# SCREEN: FETCH PRICES  (Step 2)
# ===========================================================================
def _render_fetch() -> None:
    _render_wizard_nav(2)

    products_state: list[ProductRecord] = st.session_state["products"]

    _, col, _ = st.columns([1, 4, 1])
    with col:
        st.markdown('<div class="step-heading">Fetch Market Prices</div>', unsafe_allow_html=True)

        if not products_state:
            st.markdown("""
            <div class="empty-state">
              <div class="es-title">No products loaded yet</div>
              <div class="es-hint">Go back and upload your supplier price list first.</div>
            </div>
            """, unsafe_allow_html=True)
            return

        all_suppliers = sorted({p.source for p in products_state})

        # Drop stale filter entries when the catalog changes between runs
        if "scrape_supplier_filter" in st.session_state:
            stale = set(st.session_state["scrape_supplier_filter"]) - set(all_suppliers)
            if stale:
                del st.session_state["scrape_supplier_filter"]

        running = _SB.running

        if len(all_suppliers) >= 2 and not running:
            selected = st.multiselect(
                "Suppliers to scrape",
                options=all_suppliers,
                default=st.session_state.get("scrape_supplier_filter") or all_suppliers,
                key="scrape_supplier_filter",
                help="Limit this scrape to selected suppliers. Default: all.",
            )
        else:
            selected = all_suppliers

        products_filtered = [p for p in products_state if p.source in set(selected)]

        if not products_filtered and products_state:
            st.caption("No suppliers selected — pick at least one to fetch prices.")

        cache = ScrapeCache()
        cached_count  = sum(1 for p in products_filtered if cache.has(p.barcode, p.name))
        pending_count = len(products_filtered) - cached_count

        st.markdown(
            f'<div class="step-sub"><strong style="color:var(--text-primary)">'
            f'{len(products_filtered)} products</strong> staged from {len(selected)} supplier(s). '
            f'Ready to match against live Skroutz.gr market data.</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Products",  len(products_filtered))
        c2.metric("Prices Cached",   cached_count)
        c3.metric("Need Live Fetch", pending_count)

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Request Settings", expanded=not running):
            delay   = st.slider("Delay between requests (s)", 0.0, 5.0, float(SCRAPER_DEFAULT_DELAY), step=0.1)
            max_live = st.number_input(
                "Max live API calls (0 = unlimited)", min_value=0, max_value=500, value=20, step=5,
                help="Cache hits are free and don't count. Raise to 0 for a full production run.",
            )
            headless = HEADLESS_MODE
            if SCRAPER_SOURCE == "serpapi":
                api_key = SERPAPI_KEY
                st.caption("Using Google Shopping (SerpAPI) for market prices.")
            else:
                api_key = ""
                st.caption("Using Skroutz scraper (legacy). Set SPREADSHOP_SCRAPER=serpapi to switch.")

        # ---- Background scrape worker ----
        def _scrape_thread(products, delay, headless, api_key="", max_live_requests=20) -> None:
            """Background scrape worker — delegates to scraper.runner.run_scrape."""
            import threading as _threading
            from scraper.runner import run_scrape

            stop_evt       = _threading.Event()
            _SB.stop_event = stop_evt
            _SB.scraper    = None
            _SB.running    = True
            _SB.log        = []
            _SB.progress   = 0
            _SB.total      = len(products)
            _SB.status     = ""
            _SB.counts     = {"found": 0, "not_found": 0, "cached": 0, "errors": 0}
            _SB.results    = {}
            _SB.analyses_ready = False

            def _on_cache_hit(key, r):
                _SB.results[key] = r
                _SB.counts["cached"] += 1

            def _on_result(key, r):
                _SB.results[key] = r
                _SB.counts["found" if r.found else "not_found"] += 1

            try:
                run_scrape(
                    products, api_key=api_key, delay=delay,
                    max_live_requests=max_live_requests or 0,
                    on_status=lambda msg: _SB.log.append(msg),
                    on_progress=lambda done, total: setattr(_SB, "progress", done),
                    on_result=_on_result,
                    on_cache_hit=_on_cache_hit,
                    on_scraper_ready=lambda s: setattr(_SB, "scraper", s),
                    stop_event=stop_evt,
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                _SB.log.append(f"[ERROR] Fatal: {exc}")
                _SB.counts["errors"] += 1
            finally:
                _SB.scraper        = None
                _SB.running        = False
                _SB.scraped_at     = datetime.datetime.now()
                _SB.analyses_ready = True

        # ---- Action buttons ----
        col_btn1, col_btn2, col_btn3 = st.columns(3)

        if not running:
            if col_btn1.button("Fetch Market Prices", type="primary",
                               use_container_width=True, disabled=pending_count == 0):
                _SB.running = True
                t = threading.Thread(
                    target=_scrape_thread,
                    args=(products_filtered, delay, headless,
                          st.session_state.get("serpapi_key", SERPAPI_KEY), max_live),
                    daemon=True,
                )
                t.start()
                st.rerun()

            if col_btn2.button("Use Saved Prices", use_container_width=True,
                               disabled=cached_count == 0):
                results = {}
                for p in products_filtered:
                    r = cache.get(p.barcode, p.name)
                    if r:
                        key = p.barcode if p.barcode else p.name[:60].lower()
                        results[key] = r
                st.session_state["skroutz_results"] = results
                st.session_state["analyses"]        = analyze(products_filtered, results)
                st.session_state["last_scraped_at"] = datetime.datetime.now()
                _go("results")

            if col_btn3.button("Clear Cache", use_container_width=True):
                cache.clear()
                st.session_state["skroutz_results"] = {}
                st.session_state["analyses"]        = []
                st.rerun()
        else:
            if col_btn1.button("Pause", use_container_width=True):
                s = _SB.scraper
                if s:
                    s.pause()
                st.session_state["scrape_paused"] = True

            if col_btn2.button("Resume", use_container_width=True,
                               disabled=not st.session_state["scrape_paused"]):
                s = _SB.scraper
                if s:
                    s.resume()
                st.session_state["scrape_paused"] = False

            if col_btn3.button("Stop", use_container_width=True):
                _SB.stop_event.set()
                s = _SB.scraper
                if s:
                    s.stop()

        # Progress display
        if running or _SB.progress:
            _total = _SB.total or len(products_state)
            st.progress(_SB.progress / _total if _total else 0)
            st.caption(_SB.status)

            _cnt = _SB.counts
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Found",      _cnt["found"])
            cc2.metric("Not Found",  _cnt["not_found"])
            cc3.metric("From Cache", _cnt["cached"])
            cc4.metric("Errors",     _cnt["errors"])

        if _SB.log:
            def _colorize_log(line: str) -> str:
                if "[OK]" in line or "Found:" in line:
                    return f'<span style="color:var(--accent-text)">{line}</span>'
                if "[ERROR]" in line or "Fatal" in line:
                    return f'<span style="color:var(--danger)">{line}</span>'
                if "[cache]" in line or "[LIMIT]" in line or "[WARN]" in line:
                    return f'<span style="color:var(--text-muted)">{line}</span>'
                return line
            log_html = "<br>".join(_colorize_log(l) for l in _SB.log[-30:])
            st.markdown(f'<div class="scrape-log">{log_html}</div>', unsafe_allow_html=True)

        if running:
            time.sleep(1)
            st.rerun()


# ===========================================================================
# SCREEN: RESULTS  (Step 3 — Dashboard + Analysis combined)
# ===========================================================================
def _render_results() -> None:
    import plotly.express as px

    _render_wizard_nav(3)

    analyses: list[ProductAnalysis]     = st.session_state["analyses"]
    products_state: list[ProductRecord] = st.session_state["products"]

    if not analyses:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No results yet</div>
          <div class="es-hint">Go back to <strong>Fetch Prices</strong> to pull market data first.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    found  = [a for a in analyses if a.skroutz.found]
    strong = [a for a in analyses if a.recommendation == "strong_buy"]
    avg_mg = sum(a.margin_pct for a in found) / len(found) if found else 0.0
    invest = sum(a.product.wholesale_price for a in strong)
    profit = sum(a.margin_absolute for a in strong)

    # ---- Hero metric strip ----
    st.markdown(f"""
    <div class="hero-metric-strip">
      <div class="hm-label">Est. Gross Profit &mdash; Strong Buy Items</div>
      <div class="hm-value">&euro;{profit:,.2f}</div>
      <div class="hm-sub">{len(strong)} buy signal{'s' if len(strong) != 1 else ''} &middot; {avg_mg:.1f}% avg margin</div>
    </div>
    """, unsafe_allow_html=True)

    # ---- KPI row ----
    kd1, kd2, kd3 = st.columns(3)
    kd1.metric("Total Products",   len(analyses))
    kd2.metric("Strong Buy",       len(strong))
    kd3.metric("Avg Gross Margin", f"{avg_mg:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:var(--border-subtle);margin:4px 0 16px 0'>", unsafe_allow_html=True)
    adv = st.toggle("Advanced Analysis", key="advanced_mode")
    st.markdown("<hr style='border-color:var(--border-subtle);margin:0 0 24px 0'>", unsafe_allow_html=True)

    rec_labels = {"strong_buy": "Strong Buy", "consider": "Consider",
                  "skip": "Skip", "not_found": "Not Found"}
    not_found = [a for a in analyses if not a.skroutz.found]

    # ---- Top 5 opportunities (always shown) ----
    st.markdown("#### Top Opportunities")
    top5    = analyses[:5]
    t5_cols = st.columns(len(top5))

    badge_cls = {"strong_buy": "badge-strong", "consider": "badge-consider", "skip": "badge-skip", "not_found": "badge-nf"}
    badge_lbl = {"strong_buy": "Strong Buy",   "consider": "Consider",       "skip": "Skip",       "not_found": "Not Found"}
    comp_cls  = {"Low": "green", "Medium": "amber", "High": "red", "—": ""}

    for col, a in zip(t5_cols, top5):
        p, s = a.product, a.skroutz
        card_extra = "strong-buy" if a.recommendation == "strong_buy" else ""
        link = (
            f'<a href="{s.product_url}" target="_blank" '
            f'style="font-size:0.72rem;color:var(--accent);text-decoration:none;">↗ Skroutz</a>'
            if s.found and s.product_url else ""
        )
        mg_str = f"{a.margin_pct:+.1f}%" if s.found else "—"
        cc = comp_cls.get(a.competition_level, "")
        margin_pct_capped = min(max(a.margin_pct, 0), 100) if s.found else 0
        col.markdown(f"""
        <div class="opp-card {card_extra}">
          <div class="opp-card-header">
            <span class="{badge_cls[a.recommendation]}">{badge_lbl[a.recommendation]}</span>
            {link}
          </div>
          <div class="opp-card-title" title="{p.name}">{p.name[:38]}{"…" if len(p.name)>38 else ""}</div>
          <div class="opp-card-sub">{p.source.title()} &middot; {(p.category or "—")[:22]}</div>
          <div class="opp-margin-bar"><div class="opp-margin-fill" style="width:{margin_pct_capped:.0f}%"></div></div>
          <div class="opp-card-metrics">
            <div><div class="m-label">Margin</div><div class="m-value green">{mg_str}</div></div>
            <div><div class="m-label">Score</div><div class="m-value">{a.opportunity_score:.0f}</div></div>
            <div><div class="m-label">Compet.</div><div class="m-value {cc}">{a.competition_level}</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================================================
    # SIMPLE MODE (default)
    # ============================================================
    if not adv:
        rows_simple = sorted(
            [
                {
                    "Product":        a.product.name,
                    "Supplier":       a.product.source.title(),
                    "Wholesale €":    a.product.wholesale_price,
                    "Market Price €": a.skroutz.lowest_price,
                    "Margin %":       a.margin_pct,
                    "Signal":         rec_labels.get(a.recommendation, a.recommendation),
                }
                for a in analyses
                if a.recommendation in ("strong_buy", "consider") and a.skroutz.found
            ],
            key=lambda x: x["Margin %"],
            reverse=True,
        )
        n_shown = len(rows_simple)
        if rows_simple:
            st.markdown("#### What to Stock")
            st.dataframe(
                rows_simple, use_container_width=True, hide_index=True,
                column_config={
                    "Wholesale €":    st.column_config.NumberColumn(format="€%.2f"),
                    "Market Price €": st.column_config.NumberColumn(format="€%.2f"),
                    "Margin %":       st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
            st.caption(
                f"{n_shown} product{'s' if n_shown != 1 else ''} worth stocking "
                f"({len(strong)} Strong Buy) \u00b7 Toggle Advanced Analysis above for full breakdown"
            )
        else:
            st.info("No strong buy or consider products found. Toggle Advanced Analysis above to see all results.")
        st.divider()
        st.markdown("#### Export Report")
        col_dl1, col_dl2 = st.columns([2, 5])
        xlsx_bytes = generate_xlsx(analyses, st.session_state["parse_errors"])
        col_dl1.download_button(
            label="Download XLSX Report",
            data=xlsx_bytes,
            file_name="spreadshop_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        col_dl2.caption(
            f"Includes: Opportunities \u00b7 {len(not_found)} not-found products \u00b7 Parse errors"
        )
        st.markdown("<br>", unsafe_allow_html=True)
        n_eshop = len([a for a in analyses if a.recommendation in ("strong_buy", "consider") and a.skroutz.found])
        if n_eshop > 0:
            st.markdown("#### Build Your E-Shop")
            c1, c2 = st.columns([2, 5])
            if c1.button(f"Build E-Shop ({n_eshop} products) →", type="primary", use_container_width=True):
                _go("eshop")
            c2.caption("Generate a ready-to-preview online store from your best products.")
        return

    # ============================================================
    # ADVANCED MODE
    # ============================================================
    # ---- Investment summary ----
    if invest > 0:
        roi = (profit / invest) * 100
        st.markdown(f"""
        <div class="invest-row">
          Cost <strong>&euro;{invest:,.2f}</strong>
          &nbsp;&middot;&nbsp;
          Gross profit <span class="ir-accent">&euro;{profit:,.2f}</span>
          &nbsp;&middot;&nbsp;
          ROI <strong>{roi:.1f}%</strong>
          &nbsp;&middot;&nbsp;
          {len(strong)} strong buy products
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ---- Charts ----
    if found:
        chart_l, chart_r = st.columns(2)
        with chart_l:
            st.markdown("##### Avg Margin % by Category")
            cat_margins: dict[str, list[float]] = defaultdict(list)
            for a in found:
                cat_margins[a.product.category or "Uncategorised"].append(a.margin_pct)
            cat_rows = sorted(
                [{"Category": k, "Avg Margin %": round(sum(v)/len(v), 1)} for k, v in cat_margins.items()],
                key=lambda x: x["Avg Margin %"], reverse=True,
            )
            fig_bar = px.bar(
                cat_rows, x="Avg Margin %", y="Category", orientation="h",
                color="Avg Margin %",
                color_continuous_scale=["#4A5160", "#10B981"],
                template="plotly_dark",
                height=max(260, len(cat_rows) * 34 + 60),
            )
            fig_bar.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                coloraxis_showscale=False,
                font=dict(family="Inter Tight, sans-serif", size=11, color="#7D8590"),
                yaxis=dict(autorange="reversed", gridcolor="#1F242C"),
                xaxis=dict(gridcolor="#1F242C", zeroline=False),
            )
            fig_bar.update_traces(marker_line_width=0)
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_r:
            st.markdown("##### Market Competition Distribution")
            comp_cnt = Counter(a.competition_level for a in found if a.competition_level != "—")
            comp_df  = [{"Level": k, "Count": v} for k, v in comp_cnt.items()]
            fig_pie = px.pie(
                comp_df, names="Level", values="Count", color="Level",
                color_discrete_map={"Low": "#10B981", "Medium": "#7D8590", "High": "#4A5160"},
                template="plotly_dark", hole=0.44, height=290,
            )
            fig_pie.update_layout(
                margin=dict(l=0, r=0, t=0, b=30),
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter Tight, sans-serif", size=11, color="#7D8590"),
                legend=dict(orientation="h", y=-0.12, bgcolor="rgba(0,0,0,0)"),
            )
            fig_pie.update_traces(textinfo="percent+label", textfont_size=11)
            st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()
    st.markdown("#### Full Analysis")

    # ---- Sidebar filters ----
    with st.sidebar:
        st.markdown("#### Analysis Filters")
        st.caption("Narrow down which products appear in the table below.")
        min_margin = st.slider("Min Margin %", -50, 200, 0)
        max_shops  = st.slider("Max Shop Count", 0, 100, 100)
        rec_filter = st.multiselect(
            "Buy Signal",
            ["strong_buy", "consider", "skip", "not_found"],
            default=["strong_buy", "consider", "skip", "not_found"],
            format_func=lambda x: {"strong_buy": "Strong Buy", "consider": "Consider",
                                   "skip": "Skip", "not_found": "Not Found"}.get(x, x),
        )
        sup_filter = st.multiselect(
            "Supplier",
            sorted({a.product.source.title() for a in analyses}),
            default=sorted({a.product.source.title() for a in analyses}),
            key="analysis_sup_filter",
        )

    filtered_a = [
        a for a in analyses
        if a.recommendation in rec_filter
        and a.product.source.title() in sup_filter
        and (not a.skroutz.found or (a.margin_pct >= min_margin and a.skroutz.shop_count <= max_shops))
    ]

    st.markdown(f"**{len(filtered_a)} products** matching filters")
    st.markdown("""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 18px 0;align-items:center;">
      <span style="font-size:0.72rem;color:var(--text-secondary);">
        <span style="color:var(--accent-text);font-weight:600;">&#9679; Strong Buy</span> &mdash; margin &ge;30%, few competitors. Stock these.
      </span>
      <span style="font-size:0.72rem;color:var(--border);">|</span>
      <span style="font-size:0.72rem;color:var(--text-secondary);">
        <span style="color:var(--warn);font-weight:600;">&#9679; Consider</span> &mdash; margin &ge;15%, moderate competition. Worth a small order.
      </span>
      <span style="font-size:0.72rem;color:var(--border);">|</span>
      <span style="font-size:0.72rem;color:var(--text-secondary);">
        <span style="color:var(--text-muted);font-weight:600;">&#9679; Skip</span> &mdash; low margin or too many competitors. Avoid.
      </span>
    </div>
    """, unsafe_allow_html=True)

    # ---- Stat strip ----
    sb_strong = [a for a in filtered_a if a.recommendation == "strong_buy"]
    sb_invest = sum(a.product.wholesale_price for a in sb_strong)
    sb_profit = sum(a.margin_absolute for a in sb_strong if a.skroutz.found)
    found_f   = [a for a in filtered_a if a.skroutz.found]
    avg_mg_a  = sum(a.margin_pct for a in found_f) / len(found_f) if found_f else 0

    st.markdown(f"""
    <div class="stat-strip">
      <strong>{len(sb_strong)}</strong> strong buy
      <span class="stat-sep">│</span>
      pot. profit <span class="stat-accent">&euro;{sb_profit:,.2f}</span>
      <span class="stat-sep">│</span>
      avg margin <strong>{avg_mg_a:.1f}%</strong>
      <span class="stat-sep">│</span>
      {len(found_f)} of {len(filtered_a)} found on market
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Main dataframe ----
    rows_a = []
    for a in filtered_a:
        p, s = a.product, a.skroutz
        cheap_price  = round(s.lowest_price - 0.01, 2) if s.found and s.lowest_price > 0 else None
        cheap_margin = (
            round((cheap_price - p.wholesale_price) / p.wholesale_price * 100, 1)
            if cheap_price is not None and p.wholesale_price > 0 else None
        )
        rows_a.append({
            "Product":            p.name,
            "Supplier":           p.source.title(),
            "Category":           p.category,
            "Wholesale €":        p.wholesale_price,
            "Skroutz Low €":      s.lowest_price if s.found else None,
            "Margin €":           a.margin_absolute if s.found else None,
            "Margin %":           a.margin_pct if s.found else None,
            "Undercut vs RRP %":  a.undercut_vs_retail if s.found else None,
            "Your Cheapest €":    cheap_price,
            "Margin at Cheapest": cheap_margin,
            "Shops":              s.shop_count if s.found else None,
            "Rating":             s.rating if s.found and s.rating else None,
            "Score":              a.opportunity_score,
            "Competition":        a.competition_level,
            "Recommendation":     rec_labels.get(a.recommendation, a.recommendation),
            "Link":               s.product_url if s.found else "",
        })

    st.dataframe(
        rows_a, use_container_width=True, hide_index=True,
        column_config={
            "Wholesale €":        st.column_config.NumberColumn(format="€%.2f"),
            "Skroutz Low €":      st.column_config.NumberColumn(format="€%.2f"),
            "Margin €":           st.column_config.NumberColumn(format="€%.2f"),
            "Margin %":           st.column_config.NumberColumn(format="%.1f%%"),
            "Undercut vs RRP %":  st.column_config.NumberColumn(
                format="%.1f%%",
                help="How much cheaper Skroutz low is vs. supplier's suggested retail price",
            ),
            "Your Cheapest €":    st.column_config.NumberColumn(
                format="€%.2f",
                help="Set this price to be the cheapest seller on Skroutz (market low − €0.01)",
            ),
            "Margin at Cheapest": st.column_config.NumberColumn(
                format="%.1f%%",
                help="Your gross margin if you sell at the cheapest price",
            ),
            "Rating":  st.column_config.NumberColumn(format="%.1f"),
            "Score":   st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Link":    st.column_config.LinkColumn("Skroutz Link"),
        },
    )

    # ---- Scatter chart ----
    if found:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Margin vs. Competition Map")
        scatter_data = [
            {
                "Product":    a.product.name[:55],
                "Shop Count": a.skroutz.shop_count,
                "Margin %":   a.margin_pct,
                "Score":      a.opportunity_score,
                "Rec":        rec_labels.get(a.recommendation, a.recommendation),
            }
            for a in filtered_a if a.skroutz.found
        ]
        if scatter_data:
            cmap = {"Strong Buy": "#10B981", "Consider": "#7D8590", "Skip": "#4A5160", "Not Found": "#2A2F37"}
            fig_sc = px.scatter(
                scatter_data, x="Shop Count", y="Margin %",
                size="Score", color="Rec", color_discrete_map=cmap,
                hover_name="Product",
                hover_data={"Score": True, "Shop Count": True, "Margin %": ":.1f"},
                template="plotly_dark", size_max=30, height=420,
                labels={"Shop Count": "No. of Shops (Competition)", "Margin %": "Gross Margin %"},
            )
            fig_sc.add_hline(
                y=30, line_dash="dot", line_color="rgba(16,185,129,0.33)",
                annotation_text="Strong Buy threshold (30%)", annotation_position="top right",
                annotation_font_color="rgba(16,185,129,0.60)",
            )
            fig_sc.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter Tight, sans-serif", size=11, color="#7D8590"),
                legend=dict(orientation="h", y=1.05, x=0, bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis=dict(gridcolor="#1F242C", zeroline=False),
                yaxis=dict(gridcolor="#1F242C", zeroline=True, zerolinecolor="#1F242C"),
            )
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption("Bubble size = opportunity score. Best picks: upper-left (high margin, few competitors).")

    st.divider()

    # ---- Catalog expander ----
    if products_state:
        with st.expander(f"View full catalog ({len(products_state)} products)"):
            st.caption("All products parsed from your supplier files.")
            st.dataframe(
                [
                    {
                        "Barcode":     p.barcode,
                        "Code":        p.code,
                        "Product":     p.name,
                        "Category":    p.category,
                        "Supplier":    p.source.title(),
                        "Wholesale €": p.wholesale_price,
                        "Retail €":    p.retail_price,
                    }
                    for p in products_state
                ],
                use_container_width=True, hide_index=True,
                column_config={
                    "Wholesale €": st.column_config.NumberColumn(format="€%.2f"),
                    "Retail €":    st.column_config.NumberColumn(format="€%.2f"),
                },
            )

    # ---- Export ----
    st.markdown("#### Export Report")
    col_dl1, col_dl2 = st.columns([2, 5])
    xlsx_bytes = generate_xlsx(analyses, st.session_state["parse_errors"])
    col_dl1.download_button(
        label="Download XLSX Report",
        data=xlsx_bytes,
        file_name="spreadshop_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    col_dl2.caption(
        f"Includes: Opportunities · {len(not_found)} not-found products · Parse errors"
    )

    st.markdown("<br>", unsafe_allow_html=True)
    n_eshop_adv = len([a for a in analyses if a.recommendation in ("strong_buy", "consider") and a.skroutz.found])
    if n_eshop_adv > 0:
        st.markdown("#### Build Your E-Shop")
        ca1, ca2 = st.columns([2, 5])
        if ca1.button(f"Build E-Shop ({n_eshop_adv} products) →", type="primary", use_container_width=True, key="adv_eshop_btn"):
            _go("eshop")


# ===========================================================================
# SCREEN: E-SHOP  (Step 4 — Generate & preview local e-shop)
# ===========================================================================
def _render_eshop() -> None:
    import functools
    import http.server
    import io
    import threading
    import zipfile
    from pathlib import Path

    from eshop import generate_eshop
    from eshop.site_config import COLOR_SCHEMES, FONT_OPTIONS, default_site_config

    _render_wizard_nav(4)
    ss = st.session_state

    analyses: list[ProductAnalysis] = ss.get("analyses", [])
    if not analyses:
        st.warning("No analysis data found. Go back and fetch market prices first.")
        return

    # Products eligible for the e-shop
    eligible = [a for a in analyses if a.recommendation in ("strong_buy", "consider") and a.skroutz.found]
    strong   = [a for a in eligible if a.recommendation == "strong_buy"]
    consider = [a for a in eligible if a.recommendation == "consider"]

    # ── Step heading ──────────────────────────────────────────────
    st.markdown('<div class="step-heading">Build Your E-Shop</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="step-sub">Configure your store, select products, and launch a live preview in one click.</div>',
        unsafe_allow_html=True,
    )

    # ── Store settings ────────────────────────────────────────────
    TEMPLATE_OPTIONS = {
        "t1": "Modern — gradient hero, 5-col grid, pill category filters",
        "t2": "Elevate — premium editorial, large cards, tab category nav",
        "t3": "Market  — traditional e-shop, featured products, compact grid",
    }
    with st.expander("Store Settings", expanded=True):
        cfg_c1, cfg_c2 = st.columns(2)
        with cfg_c1:
            store_name = st.text_input(
                "Store Name",
                value=ss.get("eshop_store_name") or "My Shop",
                placeholder="π.χ. Atcare Health Shop",
            )
            ss["eshop_store_name"] = store_name

            tagline = st.text_input(
                "Tagline",
                value=ss.get("eshop_tagline") or "",
                placeholder="Ποιοτικά προϊόντα σε ανταγωνιστικές τιμές",
            )
            ss["eshop_tagline"] = tagline

            headline = st.text_input(
                "Hero Headline",
                value=ss.get("eshop_headline") or "",
                placeholder="Ποιοτικά προϊόντα για κάθε ανάγκη.",
            )
            ss["eshop_headline"] = headline

            subheadline = st.text_input(
                "Hero Subheadline",
                value=ss.get("eshop_subheadline") or "",
                placeholder="Επιλεγμένα προϊόντα από αξιόπιστους προμηθευτές.",
            )
            ss["eshop_subheadline"] = subheadline

        with cfg_c2:
            scheme_options = list(COLOR_SCHEMES.keys())
            scheme_labels  = [COLOR_SCHEMES[k]["label"] for k in scheme_options]
            current_idx    = scheme_options.index(ss.get("eshop_color", "green"))
            chosen_idx     = st.selectbox(
                "Accent Color",
                range(len(scheme_options)),
                index=current_idx,
                format_func=lambda i: scheme_labels[i],
            )
            ss["eshop_color"] = scheme_options[chosen_idx]

            font_keys   = list(FONT_OPTIONS.keys())
            font_labels = [FONT_OPTIONS[k]["label"] for k in font_keys]
            current_font_idx = font_keys.index(ss.get("eshop_font", "modern"))
            chosen_font_idx  = st.selectbox(
                "Font",
                range(len(font_keys)),
                index=current_font_idx,
                format_func=lambda i: font_labels[i],
            )
            ss["eshop_font"] = font_keys[chosen_font_idx]

            logo_file = st.file_uploader(
                "Store Logo (PNG / JPG / SVG)",
                type=["png", "jpg", "jpeg", "svg"],
                help="Shown in the navigation bar. Leave empty to use store name text.",
            )
            if logo_file is not None:
                ss["eshop_logo_bytes"] = logo_file.read()
                ext = logo_file.name.rsplit(".", 1)[-1].lower()
                ss["eshop_logo_ext"]   = "svg" if ext == "svg" else ext
            if ss.get("eshop_logo_bytes"):
                st.caption(f"Logo uploaded ({ss['eshop_logo_ext'].upper()})")

        st.markdown("**Template Design**")
        tmpl_keys   = list(TEMPLATE_OPTIONS.keys())
        current_tmpl = ss.get("eshop_template", "t1")
        chosen_tmpl  = st.radio(
            "Template",
            tmpl_keys,
            index=tmpl_keys.index(current_tmpl),
            format_func=lambda k: TEMPLATE_OPTIONS[k],
            horizontal=False,
            label_visibility="collapsed",
        )
        ss["eshop_template"] = chosen_tmpl

    # ── Product selection ─────────────────────────────────────────
    st.markdown("#### Product Selection")
    col_sel_a, col_sel_b = st.columns(2)
    include_strong  = col_sel_a.checkbox(f"Include Strong Buy ({len(strong)} products)",  value=True)
    include_consider = col_sel_b.checkbox(f"Include Consider ({len(consider)} products)", value=True)

    selected = []
    if include_strong:
        selected.extend(strong)
    if include_consider:
        selected.extend(consider)

    if not selected:
        st.info("Select at least one product tier above.")
        return

    n_cats = len({(a.product.category or "Γενικά") for a in selected})
    st.caption(f"{len(selected)} products · {n_cats} categories will be included")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Generate button ───────────────────────────────────────────
    server_running = _EB.server is not None

    if not server_running:
        if st.button("Generate & Launch E-Shop", type="primary", use_container_width=False):
            output_dir = Path(ESHOP_OUTPUT_DIR)
            site_cfg   = default_site_config(
                store_name=ss.get("eshop_store_name") or "My Shop",
                color_scheme=ss.get("eshop_color", "green"),
                tagline=ss.get("eshop_tagline") or "",
                headline=ss.get("eshop_headline") or "",
                subheadline=ss.get("eshop_subheadline") or "",
                font=ss.get("eshop_font") or "modern",
            )
            # Attach logo bytes so generator can write them to static/
            site_cfg["logo_bytes"] = ss.get("eshop_logo_bytes")
            site_cfg["logo_ext"]   = ss.get("eshop_logo_ext") or "png"
            with st.spinner("Building your e-shop…"):
                generate_eshop(selected, output_dir, site_cfg, template=ss.get("eshop_template", "t1"))

            # Start local HTTP server
            class _SilentHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *_): pass

            handler = functools.partial(_SilentHandler, directory=str(output_dir))
            srv     = http.server.HTTPServer(("0.0.0.0", ESHOP_PORT), handler)
            thread  = threading.Thread(target=srv.serve_forever, daemon=True)
            thread.start()

            _EB.server     = srv
            _EB.output_dir = output_dir
            # Use the host-side URL (port is mapped 8082→8082 in docker-compose)
            ss["eshop_url"] = f"http://localhost:{ESHOP_PORT}"
            ss["eshop_output_dir"] = str(output_dir)
            st.rerun()
    else:
        # ── Running state ─────────────────────────────────────────
        eshop_url = ss.get("eshop_url", f"http://localhost:{ESHOP_PORT}")

        st.markdown(f"""
        <div class="eshop-running-row">
          <div class="eshop-running-dot"></div>
          <span>running &middot; preview at <a href="{eshop_url}" target="_blank">{eshop_url}&nbsp;&nearr;</a></span>
        </div>
        """, unsafe_allow_html=True)

        btn_c1, btn_c2 = st.columns([1, 1])

        with btn_c1:
            if st.button("Stop Server", use_container_width=True):
                if _EB.server:
                    _EB.server.shutdown()
                    _EB.server = None
                    _EB.output_dir = None
                ss["eshop_url"] = None
                st.rerun()

        with btn_c2:
            # Build ZIP in memory
            output_path = Path(ss.get("eshop_output_dir") or ESHOP_OUTPUT_DIR)
            if output_path.exists():
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fpath in output_path.rglob("*"):
                        if fpath.is_file():
                            zf.write(fpath, fpath.relative_to(output_path))
                buf.seek(0)
                st.download_button(
                    label="Download Site ZIP",
                    data=buf.read(),
                    file_name=f"{(ss.get('eshop_store_name') or 'eshop').replace(' ','-').lower()}-site.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        # Rebuild option
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Rebuild with New Settings", use_container_width=False):
            if _EB.server:
                _EB.server.shutdown()
                _EB.server = None
            ss["eshop_url"] = None
            st.rerun()


# ===========================================================================
# MAIN — screen routing
# ===========================================================================
screen = st.session_state.get("screen", "landing")

if screen == "landing":
    _render_landing()
elif screen == "upload":
    _render_upload()
elif screen == "fetch":
    _render_fetch()
elif screen == "results":
    _render_results()
elif screen == "eshop":
    _render_eshop()
else:
    _render_landing()
