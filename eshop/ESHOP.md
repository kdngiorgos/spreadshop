# Spreadshop — E-Shop Generator Module

## Purpose

The `eshop/` module takes the output of the market analysis (ranked `ProductAnalysis` objects) and generates a **complete static HTML e-shop website** ready to preview in a browser. The generated site requires no server-side runtime — it is pure HTML, CSS, and JavaScript, served by Python's built-in `http.server`.

The workflow is: Results screen → Build E-Shop (Step 4) → select products + template → click Generate → preview at `http://localhost:8082`.

---

## Module Structure

```
eshop/
├── __init__.py          # Exposes generate_eshop()
├── generator.py         # Core renderer: ProductAnalysis[] → static site
├── site_config.py       # Color schemes, default_site_config()
├── ESHOP.md             # This file
│
├── static/              # Shared static assets (copied into every generated site)
│   ├── style.css        # CSS overrides on top of Tailwind CDN
│   ├── catalog.js       # Category filter pills + live search + localStorage cart
│   └── placeholder.svg  # Default product image (200×200 box icon)
│
└── templates/           # Jinja2 template sets — one subdirectory per design
    ├── t1/              # "Modern"  — gradient hero, 5-col grid, pill filters
    │   ├── base.html.j2
    │   ├── index.html.j2
    │   └── product.html.j2
    ├── t2/              # "Elevate" — premium editorial, large cards, tab nav
    │   ├── base.html.j2
    │   ├── index.html.j2
    │   └── product.html.j2
    └── t3/              # "Market"  — traditional Greek e-shop, featured section
        ├── base.html.j2
        ├── index.html.j2
        └── product.html.j2
```

---

## Template Designs

### T1 — Modern
**Audience:** General-purpose. Works for any product category.
**Visual language:** Dark gradient hero banner, white grid body, Tailwind pill category filters, 5-column product grid. Signal badges (Top Pick / Αξίζει) on image corners. Accent-colored "Add to Cart" button. Clean DM Sans / Inter font. Inspired by modern SaaS product pages and Shopify Debut theme.
**Best for:** Health/supplements, cosmetics, home goods, food & beverage.

### T2 — Elevate
**Audience:** Premium / editorial feel. Works when brand positioning matters.
**Visual language:** White background, dark-accent header (accent-color top border), no hero banner — starts with large typography statement. 3-column grid with extra whitespace between cards. Category navigation as underline tabs (not pills). Circular "+" cart button per card. Product images are large and prominent. Inspired by Zara, Aesop, premium D2C brands.
**Best for:** Cosmetics, fashion accessories, premium food, lifestyle products, supplements.

### T3 — Market
**Audience:** Traditional Greek e-shop feel. Familiar, information-dense, trustworthy.
**Visual language:** Dark accent info bar at top (phone, email, trust signals), warmer gray background (`#f4f6f8`), white product cards with visible borders. Featured products section at top (top 3 Strong Buy products). 5-column compact grid. Visible rating stars. Red cart counter badge. Footer with trust badges (SSL, payments, couriers). Inspired by Kotsovolos, eshop.gr, Greek marketplace norms.
**Best for:** Electronics, household goods, general merchandise, multi-category shops.

---

## Generator Flow (`generator.py`)

```python
generate_eshop(analyses, output_dir, site_config, template="t1")
```

1. **Clear output dir** — `shutil.rmtree` then re-create with `product/` subdirectory
2. **Copy static assets** — `eshop/static/` → `output_dir/static/`
3. **Build product context dicts** — map each `ProductAnalysis` to a flat dict with: `id`, `name`, `category`, `price` (skroutz lowest or retail fallback), `cost` (wholesale), `margin_pct`, `skroutz_url`, `signal`, `slug`, `bg_color` (category tint)
4. **Deduplicate slugs** — append `-N` suffix for duplicate product names
5. **Build category list** — sorted by count descending
6. **Render `index.html`** — all products, categories, `static_root="static"`, `store_root="index.html"`
7. **Render `product/{slug}.html`** per product — `static_root="../static"`, `store_root="../index.html"`
8. **Write `site_config.json`** — metadata for future hosting step

### Slug generation
Greek characters are Unicode-normalized and stripped via ASCII encoding. Barcode or product code is used as fallback if the result is empty (common for Greek-only names).

### Category color tints
10 distinct hex colors are assigned to categories deterministically via `hash(category) % 10`. Same category always gets same color. Used as `background: COLOR12` (5% opacity) on product image areas, making the grid look visually varied without requiring real images.

---

## Template Variables

All templates receive these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `site` | dict | Store config: `name`, `tagline`, `headline`, `subheadline`, `accent_color`, `accent_dark`, `currency` |
| `products` | list[dict] | All products with all fields listed above |
| `categories` | list[dict] | `{name, count}` sorted by count desc |
| `product_count` | int | Total products |
| `category_count` | int | Number of unique categories |
| `year` | int | Current year (for copyright) |
| `static_root` | str | `"static"` (index) or `"../static"` (product pages) |
| `store_root` | str | `"index.html"` (index) or `"../index.html"` (product pages) |

Product pages additionally receive:
| Variable | Type | Description |
|----------|------|-------------|
| `product` | dict | Single product dict (same fields as products list) |

### Product dict fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | Barcode or code — used as cart key |
| `name` | str | Full product name |
| `category` | str | Category string (defaults to "Γενικά") |
| `price` | float | Selling price — skroutz lowest if found, else retail |
| `cost` | float | Wholesale price (internal, available in templates) |
| `margin_pct` | float | Gross margin percentage |
| `skroutz_url` | str | Skroutz product URL (empty string if not found) |
| `signal` | str | `"strong_buy"`, `"consider"`, `"skip"`, `"not_found"` |
| `slug` | str | URL-safe identifier (deduplicated) |
| `bg_color` | str | Hex tint for image background (e.g. `"#10b981"`) |

---

## JavaScript (`catalog.js`)

Handles client-side interactions with no dependencies:

- **Category filter** — `.filter-pill[data-category]` clicks → show/hide `.product-card[data-category]` cards
- **Live search** — `#search-input` input → filter cards by `data-name` substring
- **Cart** — `addToCart(id, name, price)` stores items in `localStorage["spreadshop_cart"]`. Quantity tracked. Shows `#cart-toast`. `#cart-count` badge updated.
- **Toggle cart** — `toggleCart()` on `#cart-btn` shows `alert()` summary (stub — real checkout is a future phase)

**JS hooks that templates MUST preserve** (required for catalog.js to work):
- `id="search-input"` — search text input
- `id="results-count"` — element showing "N προϊόντα" text
- `id="empty-state"` — shown when 0 results visible
- `id="cart-count"` — cart item count badge
- `id="cart-btn"` — cart button (calls `toggleCart()`)
- `id="cart-toast"` + `id="cart-toast-text"` — toast notification
- `.product-card` (or any element) with `data-category` and `data-name` attributes on each product

---

## Color Schemes

Defined in `eshop/site_config.py`:

| Key | Label | Accent | Works well for |
|-----|-------|--------|----------------|
| `green` | Πράσινο | `#10B981` | Health, food, nature |
| `blue` | Μπλε | `#3B82F6` | Tech, medical, trust |
| `purple` | Μοβ | `#8B5CF6` | Cosmetics, premium |
| `orange` | Πορτοκαλί | `#F59E0B` | Food, sport, energy |
| `red` | Κόκκινο | `#EF4444` | Sales, urgency, food |

---

## Local Server

Python's `http.server.HTTPServer` runs in a daemon thread. Port: `ESHOP_PORT` (default `8082` in `config.py`). The server instance is stored in `eshop_buffer.py` (module-level, survives Streamlit reruns — same pattern as `scrape_buffer.py`).

Stopping the server calls `server.shutdown()` and sets `_EB.server = None`.

---

## Adding a New Template

1. Create `eshop/templates/tN/` with `base.html.j2`, `index.html.j2`, `product.html.j2`
2. Follow the JS hooks contract above (keep element IDs)
3. Keep `catalog.js` — it works with any HTML structure as long as the hooks exist
4. Add the template to `TEMPLATE_OPTIONS` dict in `_render_eshop()` in `app.py`
5. Test: `generate_eshop(analyses, Path("test_output"), cfg, template="tN")`

---

## Output Directory Structure

```
eshop_output/
├── index.html           # Product catalog
├── site_config.json     # Metadata (template used, product count, site config)
├── static/
│   ├── style.css
│   ├── catalog.js
│   └── placeholder.svg
└── product/
    ├── bio-strath-forte-200-tabs.html
    ├── solgar-vitamin-d3-5000iu.html
    └── ...
```

---

## Future Phases

- **Phase 5A:** Real product images — integrate with a product image CDN or allow users to upload images per product
- **Phase 5B:** Domain name selection — `st.text_input("Domain name")` + DNS setup instructions
- **Phase 5C:** Cloud deployment — ZIP upload to Vercel/Netlify via their deploy APIs; `site_config.json` already contains all metadata needed
- **Phase 5D:** Shopping cart backend — connect to a payment processor (Stripe, Viva Wallet for Greece)
- **Phase 5E:** CMS — allow editing product names, descriptions, and prices post-generation without re-running the full wizard
