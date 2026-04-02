# Spreadshop — Design System & Style Guide

## Design Philosophy

**"Commerce Intelligence"** — a design direction built for B2B resellers who
stare at price tables all day. The interface must feel like a professional
financial tool: high information density, zero visual noise, instant
comprehension of what to buy and what to skip.

### Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Signal over decoration** | Color is reserved for meaning: green = profit, amber = caution, red = loss |
| **Data-first typography** | Numbers and prices use monospace; chrome/labels use proportional sans-serif |
| **Navy, not noir** | Deep navy-blue backgrounds instead of pure black — softer on the eyes over long sessions, signals "enterprise" not "gaming" |
| **Earned green** | The primary accent is emerald green — the color of profit. Every dominant CTA and active state reinforces the tool's purpose |
| **Breathing room** | Generous padding on cards/metrics; data tables are dense by necessity but the chrome around them is not |

---

## Industry Context

### Why these choices in 2025

**Dark enterprise SaaS** (Linear, Vercel, Planetscale, Railway) moved away from
pure-black (#000 or #0F1117) toward **deep navy/slate** (~#0A0F1E). Pure black
reads as consumer-gaming; navy-slate reads as "expensive tooling." This is the
distinction that matters for a B2B tool.

**Green as primary accent** is increasingly common in fintech and commerce
analytics (Stripe's revenue charts, Shopify's analytics, Google Merchant Center).
Indigo/purple was 2021–2023; green communicates growth and profit, which maps
directly to the job-to-be-done here.

**Inter** has become the de-facto standard for data-dense SaaS interfaces
(Figma, Linear, Notion, Vercel all use it). It has excellent legibility at
small sizes, very clear numerals, and high language coverage. Monospace fonts
in UI chrome add cognitive load without benefit; they are reserved exclusively
for data cells.

---

## Color Tokens

```css
/* Backgrounds */
--bg:             #0A0F1E;   /* page background — deep navy */
--surface:        #0F1623;   /* cards, widgets, panels */
--surface-raised: #152033;   /* hover states, input fields */

/* Borders */
--border:         #1E2D45;   /* primary border */
--border-subtle:  #162134;   /* dividers, zebra rows */

/* Accent — Emerald (profit / growth / CTA) */
--accent:         #10B981;   /* primary accent */
--accent-dim:     #064E3B;   /* accent badge backgrounds */
--accent-glow:    #10B98122; /* box-shadow glow */

/* Semantic */
--info:           #3B82F6;   /* links, neutral info */
--warn:           #F59E0B;   /* "Consider" state, warnings */
--danger:         #EF4444;   /* "Skip" state, errors */
--success:        #10B981;   /* same as accent */

/* Text */
--text-primary:   #F1F5F9;   /* headings, key values */
--text-secondary: #94A3B8;   /* labels, metadata */
--text-muted:     #475569;   /* placeholders, separators */
```

### Semantic color mapping

| Data point | Color | Rationale |
|------------|-------|-----------|
| Strong Buy badge | `#10B981` on `#064E3B` | Green = buy signal |
| Consider badge | `#F59E0B` on `#2D1A00` | Amber = proceed with caution |
| Skip badge | `#EF4444` on `#2D0000` | Red = stop signal |
| Not Found badge | `#94A3B8` on `#0F1623` | Neutral grey = no data |
| Positive margin | `#10B981` | Green = profitable |
| Negative margin | `#EF4444` | Red = loss-making |
| Competition: Low | `#10B981` | Green = opportunity |
| Competition: Medium | `#F59E0B` | Amber = caution |
| Competition: High | `#EF4444` | Red = crowded |

---

## Typography Scale

| Role | Font | Size | Weight | Usage |
|------|------|------|--------|-------|
| Page heading | Inter | 1.4rem | 700 | App title |
| Section heading | Inter | 1.0rem | 700 | Tab section titles |
| Sub-heading | Inter | 0.88rem | 600 | Card titles |
| Body / UI chrome | Inter | 0.83rem | 400 | Labels, descriptions |
| Caption / meta | Inter | 0.73rem | 400 | File names, timestamps |
| Badge text | Inter | 0.72rem | 600 | Recommendation badges |
| **Prices / numbers** | JetBrains Mono | 0.9rem | 700 | Wholesale, Skroutz prices |
| **Metric values** | JetBrains Mono | 1.9rem | 700 | KPI cards |
| **Scrape log** | JetBrains Mono | 0.78rem | 400 | Terminal-style log |

**Rule:** Monospace font is exclusively for data values. All UI labels,
headings, buttons, and metadata use Inter.

---

## Component Specifications

### Metric Cards (`[data-testid="metric-container"]`)
- Background: `--surface` with `border: 1px solid --border`
- Border-radius: `12px`
- Padding: `20px 24px`
- Value: JetBrains Mono, `1.9rem`, `--accent` color
- Label: Inter, `0.73rem`, uppercase, `--text-secondary`
- Hover: border transitions to `--accent`, box-shadow `0 0 20px --accent-glow`

### Badges
- Border-radius: `20px` (pill shape, not rectangular)
- Padding: `4px 12px`
- Font: Inter, `0.72rem`, weight 600
- No box-shadow (clean, not glowing)
- Four variants: strong, consider, skip, not-found

### Tab Bar
- Underline style (not boxed)
- Active: `--accent` bottom border, `--text-primary` color
- Inactive: `--text-muted` color, no border
- No background fills on tabs

### Status Bar
- Replaced pipe-separated string → individual pill badges
- Each pill: `background: --surface`, `border: 1px solid --border`, `border-radius: 20px`
- Status dot: 6px circle, colored per state

### Opportunity Cards
- Background: `--surface`
- Border: `1px solid --border`; strong-buy variant uses `--accent` tint
- Border-radius: `12px`
- Box-shadow on strong-buy: `0 4px 20px --accent-glow`

### Charts (Plotly)
- `paper_bgcolor`: `#0F1623`
- `plot_bgcolor`: `#0A0F1E`
- Grid lines: `#1E2D45`
- Font family: `Inter`
- Font color: `#94A3B8`
- Color scale: `["#EF4444", "#F59E0B", "#10B981"]` (danger → warn → accent)
- Pie/donut: `{"Low": "#10B981", "Medium": "#F59E0B", "High": "#EF4444"}`
- Scatter recommendation colors: `{"✅ Strong Buy": "#10B981", "🟡 Consider": "#F59E0B", "❌ Skip": "#EF4444"}`

### Buttons
- Primary: `background: #10B981`, white text, `border-radius: 8px`
- Secondary: `background: --surface`, `border: 1px solid --border`, `--text-primary`

---

## Do / Don't

| Do | Don't |
|----|-------|
| Use green for any positive/profitable data point | Use green decoratively |
| Keep borders at `1px` | Double-border or thick borders |
| Use Inter for all labels, headings, buttons | Use monospace in UI chrome |
| Reserve monospace for prices and log output | Mix fonts arbitrarily |
| Use `border-radius: 12px` on cards, `20px` on badges | Use `border-radius: 4px` (too sharp) |
| Keep backgrounds in the navy family (`#0A–#15 range`) | Introduce pure grey or warm-tinted backgrounds |
| Use `box-shadow` for depth on hover only | Always-visible heavy shadows |

---

## Streamlit Config (`config.toml`)

```toml
[theme]
base                     = "dark"
primaryColor             = "#10B981"
backgroundColor          = "#0A0F1E"
secondaryBackgroundColor = "#0F1623"
textColor                = "#F1F5F9"
font                     = "sans serif"
```

`font = "sans serif"` tells Streamlit's native widgets to use the system
sans-serif stack. Inter is loaded via a CSS `@import` in `app.py` and applied
globally, overriding the native stack cleanly.

---

## Plotly Theme Reference Block

Copy-paste this into any new chart added to `app.py`:

```python
fig.update_layout(
    paper_bgcolor="#0F1623",
    plot_bgcolor="#0A0F1E",
    font=dict(family="Inter, sans-serif", size=11, color="#94A3B8"),
    xaxis=dict(gridcolor="#1E2D45", zeroline=False),
    yaxis=dict(gridcolor="#1E2D45", zeroline=True, zerolinecolor="#1E2D45"),
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
)
```
