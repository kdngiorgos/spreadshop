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
from scraper.skroutz import SkroutzScraper
from analysis.compare import ProductAnalysis, analyze
from analysis.export import generate_xlsx
from config import HEADLESS_MODE
import scrape_buffer as _SB

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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

/* ===== BASE ===== */
html, body, [class*="css"], .stApp {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* ===== APP HEADER ===== */
.app-header {
    padding: 4px 0 20px 0;
    margin-bottom: 4px;
}
.app-wordmark {
    font-size: 1.1rem;
    font-weight: 700;
    color: #D8E4F0;
    letter-spacing: -0.01em;
    font-family: 'Inter', sans-serif;
}
.app-tagline {
    font-size: 0.72rem;
    color: #364C63;
    margin-top: 3px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-family: 'Inter', sans-serif;
}

/* ===== STATUS ROW ===== */
.status-row {
    display: flex;
    align-items: center;
    gap: 0;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #1B2B40;
}
.sr-item {
    font-size: 0.74rem;
    color: #7A90AD;
    padding-right: 16px;
    font-family: 'Inter', sans-serif;
}
.sr-item strong { color: #B8CDE0; font-weight: 600; }
.sr-item.sr-accent { color: #10B981; font-weight: 500; }
.sr-sep {
    width: 1px;
    height: 11px;
    background: #1B2B40;
    margin-right: 16px;
    flex-shrink: 0;
}
.sr-dot {
    display: inline-block;
    width: 5px; height: 5px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
    position: relative; top: -1px;
}
.sr-dot-on  { background: #10B981; }
.sr-dot-off { background: #2A3D52; }

/* ===== METRIC CARDS ===== */
[data-testid="metric-container"] {
    background: #101A2C;
    border: 1px solid #1B2B40;
    border-radius: 8px;
    padding: 20px 22px;
    transition: border-color 0.15s;
}
[data-testid="metric-container"]:hover { border-color: #2A4060; }
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.8rem !important;
    color: #D8E4F0;
    font-weight: 700;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: #7A90AD;
    font-size: 0.71rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-family: 'Inter', sans-serif !important;
}

/* ===== TABS ===== */
[data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #1B2B40 !important;
    background: transparent !important;
}
[data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 0 !important;
    padding: 9px 18px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    color: #364C63 !important;
    font-size: 0.8rem;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500;
    transition: color 0.12s;
}
[data-baseweb="tab"]:hover { color: #7A90AD !important; }
[aria-selected="true"][data-baseweb="tab"] {
    border-bottom-color: #10B981 !important;
    color: #D8E4F0 !important;
    font-weight: 600;
}

/* ===== BADGES ===== */
.badge-strong   { background:#042A1E; color:#34C991; padding:3px 10px; border-radius:4px; font-size:0.71rem; border:1px solid #10B98133; font-weight:600; font-family:'Inter',sans-serif; }
.badge-consider { background:#211800; color:#D4A017; padding:3px 10px; border-radius:4px; font-size:0.71rem; border:1px solid #D97706333; font-weight:600; font-family:'Inter',sans-serif; }
.badge-skip     { background:#200808; color:#C87070; padding:3px 10px; border-radius:4px; font-size:0.71rem; border:1px solid #DC262633; font-weight:600; font-family:'Inter',sans-serif; }
.badge-nf       { background:#0D1520; color:#3D5270; padding:3px 10px; border-radius:4px; font-size:0.71rem; border:1px solid #1B2B40;   font-weight:600; font-family:'Inter',sans-serif; }

/* ===== OPPORTUNITY CARDS ===== */
.opp-card {
    background: #101A2C;
    border: 1px solid #1B2B40;
    border-radius: 8px;
    padding: 16px 18px;
    height: 100%;
}
.opp-card.strong-buy { border-color: #10B98133; }
.opp-card-title {
    font-size: 0.83rem;
    color: #D8E4F0;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: 'Inter', sans-serif;
}
.opp-card-sub { font-size: 0.71rem; color: #364C63; margin-top: 3px; font-family: 'Inter', sans-serif; }
.opp-card-metrics { display: flex; gap: 16px; margin-top: 12px; }
.opp-card-metrics .m-label { font-size: 0.65rem; color: #364C63; text-transform: uppercase; letter-spacing: 0.06em; font-family: 'Inter', sans-serif; margin-bottom: 2px; }
.opp-card-metrics .m-value { font-size: 0.88rem; font-weight: 700; color: #D8E4F0; font-family: 'JetBrains Mono', monospace; }
.opp-card-metrics .m-value.green { color: #10B981; }
.opp-card-metrics .m-value.amber { color: #D97706; }
.opp-card-metrics .m-value.red   { color: #DC2626; }
.opp-card-footer { margin-top: 12px; display: flex; align-items: center; gap: 8px; }

/* ===== INVEST BOX ===== */
.invest-box {
    background: #101A2C;
    border: 1px solid #1B2B40;
    border-left: 3px solid #10B981;
    border-radius: 8px;
    padding: 18px 22px;
    margin: 4px 0 20px 0;
}
.invest-box-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #7A90AD;
    margin-bottom: 14px;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
}
.invest-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 7px 0;
    border-bottom: 1px solid #1B2B40;
    font-size: 0.83rem;
}
.invest-row:last-child { border-bottom: none; }
.invest-row .ir-label { color: #7A90AD; font-family: 'Inter', sans-serif; }
.invest-row .ir-value { color: #D8E4F0; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.invest-row .ir-value.green  { color: #10B981; }
.invest-row .ir-value.accent { color: #10B981; }

/* ===== SUMMARY BOXES ===== */
.summary-box {
    background: #101A2C;
    border: 1px solid #1B2B40;
    border-radius: 8px;
    padding: 18px 20px;
    text-align: center;
}
.summary-box .sb-value { font-size: 1.5rem; font-weight: 700; color: #D8E4F0; font-family: 'JetBrains Mono', monospace; }
.summary-box .sb-value.green { color: #10B981; }
.summary-box .sb-label { font-size: 0.67rem; color: #364C63; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 6px; font-family: 'Inter', sans-serif; }
.summary-box .sb-sub { font-size: 0.77rem; color: #7A90AD; margin-top: 8px; font-family: 'Inter', sans-serif; }

/* ===== SUPPLIER CARDS ===== */
.supplier-card {
    background: #101A2C;
    border: 1px solid #1B2B40;
    border-radius: 8px;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 6px;
}
.sc-type { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #364C63; background: #0B1120; border: 1px solid #1B2B40; border-radius: 3px; padding: 2px 7px; flex-shrink: 0; font-family: 'Inter', sans-serif; }
.sc-name { font-size: 0.86rem; color: #D8E4F0; font-weight: 600; font-family: 'Inter', sans-serif; }
.sc-meta { font-size: 0.71rem; color: #364C63; margin-top: 2px; font-family: 'Inter', sans-serif; }
.sc-badge { margin-left: auto; font-size: 0.7rem; padding: 3px 10px; border-radius: 4px; white-space: nowrap; flex-shrink: 0; font-weight: 600; font-family: 'Inter', sans-serif; }
.sc-badge-ok   { background:#042A1E; color:#34C991; border:1px solid #10B98133; }
.sc-badge-warn { background:#211800; color:#D4A017; border:1px solid #D9770633; }
.sc-badge-err  { background:#200808; color:#C87070; border:1px solid #DC262633; }

/* ===== EMPTY STATE ===== */
.empty-state {
    padding: 60px 0 40px 0;
    color: #364C63;
}
.es-title { font-size: 0.88rem; color: #7A90AD; font-weight: 600; margin-bottom: 8px; font-family: 'Inter', sans-serif; }
.es-hint  { font-size: 0.8rem; line-height: 1.7; color: #364C63; font-family: 'Inter', sans-serif; }
.es-hint strong { color: #7A90AD; }

/* ===== SCRAPE LOG ===== */
.scrape-log {
    background: #080F1C;
    border: 1px solid #1B2B40;
    border-radius: 6px;
    padding: 12px 14px;
    font-size: 0.76rem;
    color: #7A90AD;
    max-height: 220px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.65;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "products": [],
        "parse_errors": [],
        "parse_summary": [],
        "skroutz_results": {},
        "analyses": [],
        "scrape_paused": False,    # pause-button toggle (UI only)
        "last_scraped_at": None,   # datetime | None — set when scrape finishes
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="app-header">
  <div class="app-wordmark">Spreadshop</div>
  <div class="app-tagline">Market Intelligence &mdash; B2B Reseller Analysis</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Status row
# ---------------------------------------------------------------------------
_products_sb   = st.session_state["products"]
_analyses_sb   = st.session_state["analyses"]
_last_scraped  = st.session_state["last_scraped_at"]

_n_prod = len(_products_sb)
_n_sup  = len({p.source for p in _products_sb}) if _products_sb else 0
_dot_data = "sr-dot-on" if _products_sb else "sr-dot-off"
_data_txt = (
    f"<strong>{_n_prod} products</strong> &middot; {_n_sup} supplier(s)"
    if _products_sb else "No data loaded"
)
_dot_scrape = "sr-dot-on" if _last_scraped else "sr-dot-off"
_scrape_txt = (
    f"Last scraped <strong>{_last_scraped.strftime('%d %b %Y %H:%M')}</strong>"
    if _last_scraped else "Not scraped"
)
_n_strong = sum(1 for a in _analyses_sb if a.recommendation == "strong_buy")
_opp_txt  = f"<strong>{_n_strong}</strong> strong buy" if _analyses_sb else "&mdash;"
_opp_cls  = "sr-accent" if _analyses_sb and _n_strong > 0 else ""

st.markdown(f"""
<div class="status-row">
  <span class="sr-item"><span class="sr-dot {_dot_data}"></span>{_data_txt}</span>
  <span class="sr-sep"></span>
  <span class="sr-item"><span class="sr-dot {_dot_scrape}"></span>{_scrape_txt}</span>
  <span class="sr-sep"></span>
  <span class="sr-item {_opp_cls}">{_opp_txt}</span>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_dashboard, tab_import, tab_products, tab_scrape, tab_analysis = st.tabs([
    "Dashboard", "Import", "Products", "Scrape", "Analysis"
])


# ===========================================================================
# TAB 0 — DASHBOARD
# ===========================================================================
with tab_dashboard:
    import plotly.express as px

    _db_analyses: list[ProductAnalysis] = st.session_state["analyses"]
    _db_products: list[ProductRecord]   = st.session_state["products"]

    # ---- Empty states ----
    if not _db_products and not _db_analyses:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No data loaded</div>
          <div class="es-hint">
            Go to <strong>Import</strong>, upload your supplier XLSX or PDF price lists, then confirm &amp; load.
          </div>
        </div>
        """, unsafe_allow_html=True)

    elif _db_products and not _db_analyses:
        st.markdown(f"""
        <div class="empty-state">
          <div class="es-title">Products loaded — no market data yet</div>
          <div class="es-hint">
            <strong>{len(_db_products)} products</strong> from
            <strong>{len({p.source for p in _db_products})} supplier(s)</strong> are ready.
            Go to <strong>Scrape</strong> to fetch Skroutz prices,
            or use <strong>Cache Only</strong> if you have cached results.
          </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        # ---- Computed values ----
        _found   = [a for a in _db_analyses if a.skroutz.found]
        _strong  = [a for a in _db_analyses if a.recommendation == "strong_buy"]
        _avg_mg  = sum(a.margin_pct for a in _found) / len(_found) if _found else 0.0
        _invest  = sum(a.product.wholesale_price for a in _strong)
        _profit  = sum(a.margin_absolute for a in _strong)

        # ---- KPI Row ----
        kd1, kd2, kd3, kd4 = st.columns(4)
        kd1.metric("Total Products",          len(_db_analyses))
        kd2.metric("Strong Buy",              len(_strong))
        kd3.metric("Avg Gross Margin",        f"{_avg_mg:.1f}%")
        kd4.metric("Potential Gross Profit",  f"€{_profit:,.2f}")

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Investment Summary ----
        if _invest > 0:
            _roi = (_profit / _invest) * 100
            st.markdown(f"""
            <div class="invest-box">
              <div class="invest-box-title">Investment Summary — Strong Buy Products ({len(_strong)} items)</div>
              <div class="invest-row">
                <span class="ir-label">Total wholesale cost (1 unit each)</span>
                <span class="ir-value">€{_invest:,.2f}</span>
              </div>
              <div class="invest-row">
                <span class="ir-label">Potential gross profit (sell at Skroutz low)</span>
                <span class="ir-value green">€{_profit:,.2f}</span>
              </div>
              <div class="invest-row">
                <span class="ir-label">Gross ROI on investment</span>
                <span class="ir-value accent">{_roi:.1f}%</span>
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No strong buy products with current settings. Adjust thresholds in config.py or run a fresh scrape.")

        # ---- Top 5 Opportunities ----
        st.markdown("#### Top Opportunities")
        _top5 = _db_analyses[:5]
        _t5_cols = st.columns(len(_top5))

        _badge_cls  = {"strong_buy": "badge-strong", "consider": "badge-consider", "skip": "badge-skip", "not_found": "badge-nf"}
        _badge_lbl  = {"strong_buy": "Strong Buy",   "consider": "Consider",       "skip": "Skip",       "not_found": "Not Found"}
        _comp_color = {"Low": "#10B981", "Medium": "#F59E0B", "High": "#EF4444", "—": "#475569"}
        _comp_cls   = {"Low": "green",   "Medium": "amber",   "High": "red",     "—": ""}

        for col, a in zip(_t5_cols, _top5):
            p, s = a.product, a.skroutz
            _card_extra = "strong-buy" if a.recommendation == "strong_buy" else ""
            _link = (
                f'<a href="{s.product_url}" target="_blank" '
                f'style="font-size:0.72rem;color:#3B82F6;text-decoration:none;font-family:Inter,sans-serif;">↗ Skroutz</a>'
                if s.found and s.product_url else ""
            )
            _mg_str = f"{a.margin_pct:+.1f}%" if s.found else "—"
            _cc     = _comp_cls.get(a.competition_level, "")
            _cv     = a.competition_level

            col.markdown(f"""
            <div class="opp-card {_card_extra}">
              <div class="opp-card-title" title="{p.name}">{p.name[:38]}{"…" if len(p.name)>38 else ""}</div>
              <div class="opp-card-sub">{p.source.title()} · {(p.category or "—")[:22]}</div>
              <div class="opp-card-metrics">
                <div><div class="m-label">Margin</div><div class="m-value green">{_mg_str}</div></div>
                <div><div class="m-label">Score</div><div class="m-value">{a.opportunity_score:.0f}</div></div>
                <div><div class="m-label">Compet.</div><div class="m-value {_cc}">{_cv}</div></div>
              </div>
              <div class="opp-card-footer">
                <span class="{_badge_cls[a.recommendation]}">{_badge_lbl[a.recommendation]}</span>
                {_link}
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.divider()

        # ---- Charts ----
        if _found:
            chart_l, chart_r = st.columns(2)

            # (a) Avg Margin % by Category
            with chart_l:
                st.markdown("##### Avg Margin % by Category")
                _cat_margins: dict[str, list[float]] = defaultdict(list)
                for a in _found:
                    _cat_margins[a.product.category or "Uncategorised"].append(a.margin_pct)
                _cat_rows = sorted(
                    [{"Category": k, "Avg Margin %": round(sum(v)/len(v), 1)} for k, v in _cat_margins.items()],
                    key=lambda x: x["Avg Margin %"], reverse=True,
                )
                _fig_bar = px.bar(
                    _cat_rows, x="Avg Margin %", y="Category", orientation="h",
                    color="Avg Margin %",
                    color_continuous_scale=["#EF4444", "#F59E0B", "#10B981"],
                    template="plotly_dark",
                    height=max(260, len(_cat_rows) * 34 + 60),
                )
                _fig_bar.update_layout(
                    margin=dict(l=0, r=0, t=0, b=0),
                    paper_bgcolor="#0F1623", plot_bgcolor="#0A0F1E",
                    coloraxis_showscale=False,
                    font=dict(family="Inter, sans-serif", size=11, color="#94A3B8"),
                    yaxis=dict(autorange="reversed", gridcolor="#1E2D45"),
                    xaxis=dict(gridcolor="#1E2D45", zeroline=False),
                )
                _fig_bar.update_traces(marker_line_width=0)
                st.plotly_chart(_fig_bar, use_container_width=True)

            # (b) Competition distribution donut
            with chart_r:
                st.markdown("##### Market Competition Distribution")
                _comp_cnt = Counter(
                    a.competition_level for a in _found if a.competition_level != "—"
                )
                _comp_df = [{"Level": k, "Count": v} for k, v in _comp_cnt.items()]
                _fig_pie = px.pie(
                    _comp_df, names="Level", values="Count",
                    color="Level",
                    color_discrete_map={"Low": "#10B981", "Medium": "#F59E0B", "High": "#EF4444"},
                    template="plotly_dark", hole=0.44, height=290,
                )
                _fig_pie.update_layout(
                    margin=dict(l=0, r=0, t=0, b=30),
                    paper_bgcolor="#0F1623",
                    font=dict(family="Inter, sans-serif", size=11, color="#94A3B8"),
                    legend=dict(orientation="h", y=-0.12, bgcolor="rgba(0,0,0,0)"),
                )
                _fig_pie.update_traces(textinfo="percent+label", textfont_size=11)
                st.plotly_chart(_fig_pie, use_container_width=True)


# ===========================================================================
# TAB 1 — IMPORT
# ===========================================================================
with tab_import:
    st.markdown("### Upload Supplier Files")
    st.caption("Accepts `.xlsx` and `.pdf` — multiple files supported.")

    uploaded = st.file_uploader(
        "Drop files here",
        type=["xlsx", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded:
        products: list[ProductRecord] = []
        errors: list[ParseError] = []
        summary: list[dict] = []
        ui_warnings: list[str] = []

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
                    "File":         f.name,
                    "Supplier":     supplier,
                    "Type":         f.name.rsplit(".", 1)[-1].upper(),
                    "Products":     len(ps),
                    "Parse Errors": len(es),
                    "Status":       "OK" if not es else f"{len(es)} warning(s)",
                })
            except Exception as exc:
                summary.append({
                    "File":         f.name,
                    "Supplier":     "—",
                    "Type":         "—",
                    "Products":     0,
                    "Parse Errors": 1,
                    "Status":       f"Error: {exc}",
                })

        # Unknown supplier warnings
        for w in ui_warnings:
            st.warning(w)

        st.markdown(f"**{len(products)} products** loaded from **{len(uploaded)} file(s)**")

        # Supplier cards
        for row in summary:
            _bc = ("sc-badge-ok"
                   if row["Parse Errors"] == 0
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
            if st.button("Confirm & Load Products", type="primary", use_container_width=True):
                st.session_state["products"]      = products
                st.session_state["parse_errors"]  = errors
                st.session_state["parse_summary"] = summary
                st.session_state["analyses"]      = []  # reset downstream
                st.rerun()  # force clean refresh so status bar + dashboard update immediately

    elif st.session_state["products"]:
        n = len(st.session_state["products"])
        st.info(f"**{n} products** already loaded. Upload new files to replace them.")
        for row in st.session_state.get("parse_summary", []):
            _bc = ("sc-badge-ok"
                   if row["Parse Errors"] == 0
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
    else:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No supplier files loaded</div>
          <div class="es-hint">
            Drop your <strong>.xlsx</strong> or <strong>.pdf</strong> price lists above.
            Supported: <strong>Bio Tonics / Atcare</strong> (XLSX or PDF),
            <strong>VioGenesis</strong> (PDF).
          </div>
        </div>
        """, unsafe_allow_html=True)


# ===========================================================================
# TAB 2 — PRODUCTS
# ===========================================================================
with tab_products:
    products_state: list[ProductRecord] = st.session_state["products"]

    if not products_state:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No products loaded</div>
          <div class="es-hint">Go to <strong>Import</strong> and upload supplier files first.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        suppliers  = sorted({p.source.title() for p in products_state})
        categories = sorted({p.category for p in products_state if p.category})

        with st.sidebar:
            st.markdown("#### Filters")
            sel_supplier = st.multiselect("Supplier", suppliers, default=suppliers)
            sel_category = st.multiselect("Category", categories, default=categories)
            _wh_max = float(max(p.wholesale_price for p in products_state) + 1)
            price_min, price_max = st.slider(
                "Wholesale price (€)", 0.0, _wh_max, (0.0, _wh_max),
            )

        filtered = [
            p for p in products_state
            if p.source.title() in sel_supplier
            and (not sel_category or p.category in sel_category)
            and price_min <= p.wholesale_price <= price_max
        ]

        st.markdown(f"**{len(filtered)} products** · {len(suppliers)} supplier(s)")
        st.caption(", ".join(
            f"{s}: {sum(1 for p in products_state if p.source.title()==s)}"
            for s in suppliers
        ))

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
                    "Markup %":    round(((p.retail_price - p.wholesale_price) / p.wholesale_price) * 100, 1) if p.wholesale_price > 0 else 0,
                }
                for p in filtered
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wholesale €": st.column_config.NumberColumn(format="€%.2f"),
                "Retail €":    st.column_config.NumberColumn(format="€%.2f"),
                "Markup %":    st.column_config.NumberColumn(format="%.1f%%"),
            },
        )


# ===========================================================================
# TAB 3 — SCRAPE
# ===========================================================================
with tab_scrape:
    # ------------------------------------------------------------------
    # Sync: if the background thread just finished, copy results to session
    # state so the Analysis tab and status bar pick them up.
    # ------------------------------------------------------------------
    if _SB.analyses_ready:
        st.session_state["skroutz_results"] = dict(_SB.results)
        st.session_state["last_scraped_at"] = _SB.scraped_at
        st.session_state["analyses"] = analyze(
            st.session_state["products"],
            st.session_state["skroutz_results"],
        )
        _SB.analyses_ready = False
        st.rerun()

    products_state = st.session_state["products"]

    if not products_state:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No products to scrape</div>
          <div class="es-hint">Load products from the <strong>Import</strong> tab first.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        cache = ScrapeCache()
        cached_count  = sum(1 for p in products_state if cache.has(p.barcode, p.name))
        pending_count = len(products_state) - cached_count

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Products", len(products_state))
        c2.metric("Cached",         cached_count)
        c3.metric("Pending Scrape", pending_count)

        st.divider()

        running = _SB.running

        with st.expander("Scrape Settings", expanded=not running):
            col_a, col_b, col_c = st.columns(3)
            delay = col_a.slider("Delay between requests (s)", 3, 12, 5)
            if HEADLESS_MODE:
                col_b.checkbox("Headless (hide browser)", value=True, disabled=True)
                headless = True
                col_c.caption("ℹ️ Running in Docker — headless mode is forced.")
            else:
                headless = col_b.checkbox("Headless (hide browser)", value=False)
                col_c.caption("ℹ️ Headed mode is safer against bot detection.")

        # ------------------------------------------------------------------
        def _scrape_thread(products, delay, headless) -> None:
            """Background scrape worker — writes to _SB (scrape_buffer module)."""
            _thread_cache = ScrapeCache()
            scraper = SkroutzScraper(
                headless=headless,
                delay=delay,
                on_status=lambda msg: _SB.log.append(msg),
            )
            # Reset buffer for this run
            _SB.scraper  = scraper
            _SB.running  = True
            _SB.log      = []
            _SB.progress = 0
            _SB.total    = 0
            _SB.status   = ""
            _SB.counts   = {"found": 0, "not_found": 0, "cached": 0, "errors": 0}
            _SB.results  = {}
            _SB.analyses_ready = False
            counts = _SB.counts

            try:
                scraper.start()

                # Selector health check before bulk run
                ok, hc_msg = scraper.verify_selectors()
                _SB.log.append(f"[{'OK' if ok else 'WARN'}] Health check: {hc_msg}")
                if not ok:
                    _SB.log.append("[WARN] Proceeding — results may be incomplete if Skroutz HTML changed.")

                total = len(products)
                _SB.total = total

                for i, p in enumerate(products):
                    if scraper._stop:
                        break

                    _SB.status   = f"[{i+1}/{total}] {p.name[:60]}"
                    _SB.progress = i + 1

                    cached_item = _thread_cache.get(p.barcode, p.name)
                    if cached_item is not None:
                        counts["cached"] += 1
                        key = p.barcode if p.barcode else p.name[:60].lower()
                        _SB.results[key] = cached_item
                        continue

                    result = scraper.search(p)
                    key = p.barcode if p.barcode else p.name[:60].lower()
                    _SB.results[key] = result
                    _thread_cache.put(p.barcode, p.name, result)

                    if result.found:
                        counts["found"] += 1
                    else:
                        counts["not_found"] += 1

            except Exception as exc:
                _SB.log.append(f"[ERROR] Fatal: {exc}")
                counts["errors"] += 1
            finally:
                scraper.stop()
                _SB.scraper     = None
                _SB.running     = False
                _SB.scraped_at  = datetime.datetime.now()
                _SB.log.append("[OK] Scrape complete.")
                _SB.analyses_ready = True  # signal UI to pick up results on next rerun

        # ------------------------------------------------------------------
        col_btn1, col_btn2, col_btn3 = st.columns(3)

        if not running:
            if col_btn1.button("Start Scraping", type="primary",
                               use_container_width=True, disabled=pending_count == 0):
                _SB.running = True   # set before thread start to avoid race on first rerun
                t = threading.Thread(
                    target=_scrape_thread,
                    args=(products_state, delay, headless),
                    daemon=True,
                )
                t.start()
                st.rerun()

            if col_btn2.button("Use Cache Only", use_container_width=True,
                               disabled=cached_count == 0):
                results = {}
                for p in products_state:
                    r = cache.get(p.barcode, p.name)
                    if r:
                        key = p.barcode if p.barcode else p.name[:60].lower()
                        results[key] = r
                st.session_state["skroutz_results"] = results
                st.session_state["analyses"]        = analyze(products_state, results)
                st.session_state["last_scraped_at"] = datetime.datetime.now()
                st.success(f"Loaded {len(results)} cached results. Check the **Analysis** tab.")

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
            log_html = "<br>".join(_SB.log[-30:])
            st.markdown(f'<div class="scrape-log">{log_html}</div>', unsafe_allow_html=True)

        if running:
            time.sleep(1)
            st.rerun()


# ===========================================================================
# TAB 4 — ANALYSIS
# ===========================================================================
with tab_analysis:
    analyses: list[ProductAnalysis] = st.session_state["analyses"]
    products_state = st.session_state["products"]

    if not products_state:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No data to analyse</div>
          <div class="es-hint">Load products from <strong>Import</strong>, then scrape or load cached results.</div>
        </div>
        """, unsafe_allow_html=True)
    elif not analyses:
        st.markdown("""
        <div class="empty-state">
          <div class="es-title">No analysis data yet</div>
          <div class="es-hint">
            Run the <strong>Scrape</strong> tab (or use <strong>Cache Only</strong>)
            to fetch Skroutz prices, then analysis will appear here.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        found     = [a for a in analyses if a.skroutz.found]
        not_found = [a for a in analyses if not a.skroutz.found]

        avg_margin = sum(a.margin_pct for a in found) / len(found) if found else 0
        avg_shops  = sum(a.skroutz.shop_count for a in found) / len(found) if found else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Products",       len(analyses))
        k2.metric("Found on Skroutz",     f"{len(found)} / {len(analyses)}")
        k3.metric("Avg Gross Margin",     f"{avg_margin:.1f}%")
        k4.metric("Avg Shop Competition", f"{avg_shops:.1f}")

        st.divider()

        # ---- Sidebar filters ----
        with st.sidebar:
            st.markdown("#### Analysis Filters")
            min_margin   = st.slider("Min Margin %", -50, 200, 0)
            max_shops    = st.slider("Max Shop Count", 0, 100, 100)
            rec_filter   = st.multiselect(
                "Recommendation",
                ["strong_buy", "consider", "skip", "not_found"],
                default=["strong_buy", "consider", "skip", "not_found"],
                format_func=lambda x: {"strong_buy": "Strong Buy", "consider": "Consider", "skip": "Skip", "not_found": "Not Found"}.get(x, x),
            )
            sup_filter   = st.multiselect(
                "Supplier",
                sorted({a.product.source.title() for a in analyses}),
                default=sorted({a.product.source.title() for a in analyses}),
            )

        filtered_a = [
            a for a in analyses
            if a.recommendation in rec_filter
            and a.product.source.title() in sup_filter
            and (not a.skroutz.found or (a.margin_pct >= min_margin and a.skroutz.shop_count <= max_shops))
        ]

        st.markdown(f"**{len(filtered_a)} products** matching filters")

        # ---- Business Summary ----
        _sb_strong  = [a for a in filtered_a if a.recommendation == "strong_buy"]
        _sb_invest  = sum(a.product.wholesale_price for a in _sb_strong)
        _sb_profit  = sum(a.margin_absolute for a in _sb_strong if a.skroutz.found)
        _found_f    = [a for a in filtered_a if a.skroutz.found]
        _avg_mkt    = sum(a.skroutz.lowest_price for a in _found_f) / len(_found_f) if _found_f else 0
        _avg_wh     = sum(a.product.wholesale_price for a in _found_f) / len(_found_f) if _found_f else 0

        bs1, bs2, bs3 = st.columns(3)
        bs1.markdown(f"""
        <div class="summary-box">
          <div class="sb-value">{len(_sb_strong)}</div>
          <div class="sb-label">Strong Buy Products</div>
          <div class="sb-sub">Stock cost: <strong>€{_sb_invest:,.2f}</strong></div>
        </div>
        """, unsafe_allow_html=True)
        bs2.markdown(f"""
        <div class="summary-box">
          <div class="sb-value green">€{_sb_profit:,.2f}</div>
          <div class="sb-label">Potential Gross Profit</div>
          <div class="sb-sub">From strong-buy items in current filter</div>
        </div>
        """, unsafe_allow_html=True)
        bs3.markdown(f"""
        <div class="summary-box">
          <div class="sb-value">€{_avg_mkt:.2f}</div>
          <div class="sb-label">Avg Skroutz Price</div>
          <div class="sb-sub">vs avg wholesale <strong>€{_avg_wh:.2f}</strong></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Main dataframe ----
        _rec_labels = {
            "strong_buy": "Strong Buy",
            "consider":   "Consider",
            "skip":       "Skip",
            "not_found":  "Not Found",
        }
        rows_a = []
        for a in filtered_a:
            p, s = a.product, a.skroutz
            _cheap_price  = round(s.lowest_price - 0.01, 2) if s.found and s.lowest_price > 0 else None
            _cheap_margin = (
                round((_cheap_price - p.wholesale_price) / p.wholesale_price * 100, 1)
                if _cheap_price is not None and p.wholesale_price > 0 else None
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
                "Your Cheapest €":    _cheap_price,
                "Margin at Cheapest": _cheap_margin,
                "Shops":              s.shop_count if s.found else None,
                "Rating":             s.rating if s.found and s.rating else None,
                "Score":              a.opportunity_score,
                "Competition":        a.competition_level,
                "Recommendation":     _rec_labels.get(a.recommendation, a.recommendation),
                "Link":               s.product_url if s.found else "",
            })

        st.dataframe(
            rows_a,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wholesale €":       st.column_config.NumberColumn(format="€%.2f"),
                "Skroutz Low €":     st.column_config.NumberColumn(format="€%.2f"),
                "Margin €":          st.column_config.NumberColumn(format="€%.2f"),
                "Margin %":          st.column_config.NumberColumn(format="%.1f%%"),
                "Undercut vs RRP %": st.column_config.NumberColumn(
                    format="%.1f%%",
                    help="How much cheaper Skroutz low is vs. supplier's suggested retail price",
                ),
                "Your Cheapest €":   st.column_config.NumberColumn(
                    format="€%.2f",
                    help="Set this price to be the cheapest seller on Skroutz (market low − €0.01)",
                ),
                "Margin at Cheapest": st.column_config.NumberColumn(
                    format="%.1f%%",
                    help="Your gross margin if you sell at the cheapest price",
                ),
                "Rating":  st.column_config.NumberColumn(format="⭐ %.1f"),
                "Score":   st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                "Link":    st.column_config.LinkColumn("Skroutz Link"),
            },
        )

        # ---- Scatter chart: Margin vs Competition ----
        if found:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### Margin vs. Competition Map")
            _scatter_data = [
                {
                    "Product":    a.product.name[:55],
                    "Shop Count": a.skroutz.shop_count,
                    "Margin %":   a.margin_pct,
                    "Score":      a.opportunity_score,
                    "Rec":        _rec_labels.get(a.recommendation, a.recommendation),
                }
                for a in filtered_a if a.skroutz.found
            ]
            if _scatter_data:
                import plotly.express as px
                _cmap = {
                    "Strong Buy": "#10B981",
                    "Consider":  "#D97706",
                    "Skip":      "#DC2626",
                    "Not Found": "#364C63",
                }
                _fig_sc = px.scatter(  # noqa: F821
                    _scatter_data,
                    x="Shop Count", y="Margin %",
                    size="Score", color="Rec",
                    color_discrete_map=_cmap,
                    hover_name="Product",
                    hover_data={"Score": True, "Shop Count": True, "Margin %": ":.1f"},
                    template="plotly_dark", size_max=30, height=420,
                    labels={"Shop Count": "No. of Shops (Competition)", "Margin %": "Gross Margin %"},
                )
                _fig_sc.add_hline(
                    y=30, line_dash="dot", line_color="#10B98155",
                    annotation_text="Strong Buy threshold (30%)",
                    annotation_position="top right",
                    annotation_font_color="#10B98199",
                )
                _fig_sc.update_layout(
                    paper_bgcolor="#0F1623", plot_bgcolor="#0A0F1E",
                    font=dict(family="Inter, sans-serif", size=11, color="#94A3B8"),
                    legend=dict(orientation="h", y=1.05, x=0, bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=30, b=0),
                    xaxis=dict(gridcolor="#1E2D45", zeroline=False),
                    yaxis=dict(gridcolor="#1E2D45", zeroline=True, zerolinecolor="#1E2D45"),
                )
                st.plotly_chart(_fig_sc, use_container_width=True)
                st.caption("Bubble size = opportunity score. Best picks: upper-left quadrant (high margin, few competitors).")

        st.divider()

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
