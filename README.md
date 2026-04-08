# Spreadshop

**Market intelligence for Greek resellers.** Upload a supplier price list, fetch live market prices from Skroutz.gr, and get a ranked list of which products are worth stocking — by margin, competition, and demand.

Built with Streamlit · Python 3.11 · httpx async · SerpAPI / Skroutz JSON

---

## Screenshots

| Landing | Upload |
|---|---|
| ![Landing](docs/screenshot_landing.png) | ![Upload](docs/screenshot_upload.png) |

| Fetch Prices | Results |
|---|---|
| ![Fetch](docs/screenshot_fetch.png) | ![Results](docs/screenshot_results.png) |

---

## What It Does

Greek resellers deal with supplier catalogs (XLSX/PDF) containing hundreds of products and wholesale prices. Without knowing what those products sell for on Skroutz.gr — Greece's dominant price-comparison marketplace — it's impossible to know which items are profitable.

Spreadshop solves this in three steps:

```
Upload catalog  →  Fetch live prices  →  See what to stock
    (XLSX/PDF)        (async, cached)        (margin ranked)
```

For each product it calculates gross margin, competition level, and an opportunity score. Products are recommended as **Strong Buy**, **Consider**, or **Skip**.

---

## Features

- **Guided wizard flow** — Landing page → Upload → Fetch Prices → Results. No tabs to hunt through.
- **Universal catalog parsing** — Reads supplier XLSX files and PDFs, including garbled-column VioGenesis PDFs with a purpose-built regex decoder.
- **Fast async scraping** — `httpx.AsyncClient` with configurable concurrency (default 2 workers). No browser required.
- **Two scraper backends** — Switch between the native Skroutz JSON endpoint (free, fast) and Google Shopping via SerpAPI (more reliable, requires API key).
- **Smart caching** — Results cached for 24 hours by barcode. Re-running is instant.
- **Simple / Advanced Results toggle** — Simple mode shows a clean "What to Stock" table. Advanced mode unlocks investment summary, charts, scatter plot, sidebar filters, and full 15-column analysis table.
- **XLSX report export** — Multi-sheet report with opportunities, not-found products, and parse errors.
- **Docker-ready** — Single `docker compose up` command.

---

## Wizard Flow

```
┌─────────────────────────────────────────────────────────┐
│                      LANDING                            │
│  "Find the profit hiding in your supplier's catalog."   │
│              [ Get Started → ]                          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              STEP 1 — Load Your Catalog           ● ○ ○ │
│  Drop XLSX or PDF. Auto-parsed, summary shown.          │
│              [ Confirm & Continue → ]                   │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 2 — Fetch Market Prices            ● ● ○ │
│  207 products staged. Concurrency, delay, cap.          │
│  [ Fetch Market Prices ]  [ Use Saved Prices ]          │
│  ████████████░░░░░░░░  42/207  live progress            │
└─────────────────────────┬───────────────────────────────┘
                          │  auto-navigates when done
                          ▼
┌─────────────────────────────────────────────────────────┐
│               STEP 3 — Your Results               ● ● ● │
│  Est. Gross Profit  €3,450.00                           │
│  12 buy signals · 34.5% avg margin                      │
│                                                         │
│  ○ Advanced Analysis  ←── toggle                        │
│                                                         │
│  SIMPLE:  What to Stock table (6 columns)               │
│  ADVANCED: charts, filters, full table, scatter         │
│                                                         │
│  [ Download XLSX Report ]                               │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Docker (recommended)

```bash
# 1. Clone
git clone https://github.com/kdngiorgos/spreadshop.git
cd spreadshop

# 2. Create .env with your SerpAPI key
echo "SERPAPI_KEY=your_key_here" > .env

# 3. Build and run
docker compose up -d --build

# 4. Open
open http://localhost:8080
```

The cache, reports, and logs directories are volume-mounted so they persist across container restarts.

### Local (dev)

```bash
# Python 3.11+
pip install -r requirements.txt

# Add SERPAPI_KEY to .env (or skip if using the Skroutz backend)
echo "SERPAPI_KEY=your_key_here" > .env

streamlit run app.py
# → http://localhost:8501
```

---

## Configuration

All settings live in `.env` (never committed). Copy this template:

```dotenv
# Required for SerpAPI backend
SERPAPI_KEY=your_serpapi_key_here

# Optional overrides (defaults shown)
SPREADSHOP_SCRAPER=serpapi          # "serpapi" or "skroutz"
SPREADSHOP_HEADLESS=false           # set true in Docker
```

Full list of tuneable constants in `config.py`:

| Constant | Default | Description |
|---|---|---|
| `SCRAPER_DEFAULT_DELAY` | `1.5s` | Base delay between requests |
| `SCRAPER_DEFAULT_JITTER` | `0.5s` | ±random jitter added to delay |
| `SCRAPER_CONCURRENCY` | `2` | Parallel async workers |
| `SCRAPER_MAX_RETRIES` | `3` | Retries on HTTP 429/503 |
| `SCRAPER_FUZZY_MATCH_THRESHOLD` | `0.35` | Min title similarity for a valid match |
| `CACHE_TTL_SECONDS` | `86400` | Cache lifetime (24 hours) |
| `MARGIN_STRONG_BUY_PCT` | `30%` | Minimum margin for Strong Buy |
| `MARGIN_CONSIDER_PCT` | `15%` | Minimum margin for Consider |
| `SHOPS_STRONG_BUY_MAX` | `10` | Max shops to qualify for Strong Buy |

---

## Supported Supplier Formats

### Bio Tonics — XLSX

Sheet: `Table 1`. Columns: `ΚΩΔΙΚΟΣ` (code), `ΠΕΡΙΓΡΑΦΗ` (name), `ΧΤ` (wholesale), `ΠΛΤ` (retail), `BARCODE`. Category header rows (text in col A, other cols empty) are detected and used to tag subsequent product rows.

### Bio Tonics — PDF

Same layout as XLSX, extracted via pdfplumber. Prices are comma-decimal strings (`"7,02"` → `7.02`). One known garbled row is handled by a regex that extracts `(\d+)[,.](\d{1,2})` from the raw cell value.

### VioGenesis — PDF

Complex garbled format where adjacent column text is interleaved in the price cells. Three purpose-built regex patterns decode the wholesale and retail prices:

| Pattern | Coverage | Example raw → decoded |
|---|---|---|
| Main | ~70 products | `gsr2//22w,401 €` → `22.40` |
| Single-digit | ~11 products | `gsr/9/2,w608 €` → `9.60` |
| Ads variant | ~2 products | `ads3/52,0071` → `35.00` |

All prices are validated against the expected wholesale/retail ratio (`0.48 – 0.78`). Rows outside this range are flagged as parse errors and excluded.

### Adding a new supplier

1. Create `parsers/pdf_newsupplier.py` (model it after `parsers/pdf_biotonics.py`)
2. Register it in `parsers/base.py` `parse_file()`:
   ```python
   if "suppliername" in name_lower:
       from .pdf_newsupplier import parse_newsupplier_pdf
       return parse_newsupplier_pdf(path)
   ```
3. Run `python scripts/demo.py` to validate

---

## Scraper Backends

### Skroutz (native JSON)

Uses Skroutz's own internal search endpoint with `httpx.AsyncClient` — no browser, no HTML parsing.

```
GET https://www.skroutz.gr/search.json?keyphrase={product_name}
```

1. If the response has a `redirectUrl`, follows it (`.html` → `.json`) to get the SKU list
2. Fuzzy-matches the best SKU by title similarity
3. Fetches `filter_products.json` for that SKU to get accurate per-variant prices and shop count
4. Falls back to barcode search if name search fails

**Pros:** Free, fast (no API quota), real Skroutz data  
**Cons:** Subject to Skroutz rate limits / structure changes

### SerpAPI (Google Shopping)

Uses the [SerpAPI](https://serpapi.com) Google Shopping engine with Greek locale:

```
GET https://serpapi.com/search.json?engine=google_shopping&q={name}&hl=el&gl=gr
```

1. Returns up to 10 Shopping listings; picks best by fuzzy title match
2. Counts distinct `.gr` domain sources as Greek market shop count
3. Falls back to barcode search if name search confidence is below threshold
4. Exponential backoff on HTTP 429

**Pros:** More reliable, avoids Skroutz anti-scraping  
**Cons:** Requires a paid API key; shop count is a proxy, not exact Skroutz data

Switch backends via `.env`: `SPREADSHOP_SCRAPER=skroutz` or `SPREADSHOP_SCRAPER=serpapi`.

---

## Analysis Logic

### Per-product metrics

```python
margin_absolute = skroutz_lowest_price - wholesale_price
margin_pct      = (margin_absolute / wholesale_price) × 100

competition_level = "Low"    # ≤ 4 shops
                 = "Medium"  # 5–15 shops
                 = "High"    # > 15 shops
```

### Opportunity score (0–100)

```
margin_score  = min(margin_pct / 100, 1.0) × 50   # 50% weight
comp_score    = max(0, (30 - shop_count) / 30) × 30  # 30% weight
demand_score  = min(review_count / 100, 1.0) × 20  # 20% weight
score         = margin_score + comp_score + demand_score
```

### Recommendation labels

| Label | Condition |
|---|---|
| `Strong Buy` | margin ≥ 30% **and** shops ≤ 10 |
| `Consider` | margin ≥ 15% |
| `Skip` | margin < 15% or not profitable |
| `Not Found` | product not matched on market |

---

## CLI — Scrape Without the UI

Test the scraper from the terminal without launching Streamlit:

```bash
# Scrape first 5 products from all supplier files
python scripts/scrape_cli.py --limit 5

# Filter by product name
python scripts/scrape_cli.py --product "ginseng" --limit 1

# Use a specific API key
python scripts/scrape_cli.py --api-key sk-... --limit 10
```

Output:

```
PRODUCT                                        WHOLESALE     MARKET   MARGIN  SHOPS
══════════════════════════════════════════════════════════════════════════════════
Bio-Strath Forte 200 tabs                          12.50      28.90    131.2%      6
Solgar Vitamin D3 5000iu 120 softgels              15.20      31.50    107.2%      9
...
```

---

## Project Structure

```
spreadshop/
│
├── app.py                      # Streamlit UI — wizard flow, 4 screens
│
├── parsers/
│   ├── base.py                 # ProductRecord, SkroutzResult, ParseError · parse_file()
│   ├── xlsx_parser.py          # Bio Tonics XLSX (openpyxl)
│   ├── pdf_biotonics.py        # Bio Tonics PDF (pdfplumber)
│   └── pdf_viogenesis.py       # VioGenesis PDF (pdfplumber + garble decoder)
│
├── scraper/
│   ├── __init__.py             # get_scraper() factory
│   ├── skroutz.py              # Native Skroutz JSON endpoint client
│   ├── serpapi_client.py       # SerpAPI Google Shopping client
│   ├── runner.py               # run_scrape() — shared by UI, CLI, and tests
│   └── cache.py                # JSON file cache (24h TTL, keyed by barcode)
│
├── analysis/
│   ├── compare.py              # Margin %, opportunity score, recommendations
│   └── export.py               # Multi-sheet XLSX report (openpyxl)
│
├── scripts/
│   └── scrape_cli.py           # Standalone CLI scraper
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── test_xlsx_parser.py
│   ├── test_pdf_biotonics.py
│   ├── test_pdf_viogenesis.py
│   ├── test_parse_dispatch.py
│   └── test_scraper.py
│
├── scrape_buffer.py            # Module-level shared state for background thread
├── config.py                   # All tuneable constants + env loading
├── logger.py                   # Logging setup
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .streamlit/
    └── config.toml             # Dark theme (DM Sans/DM Mono, green accent)
```

---

## Development

### Running tests

```bash
pip install pytest pytest-asyncio
pytest
```

### Linting / type checks

```bash
pip install ruff mypy
ruff check .
mypy app.py scraper/ parsers/ analysis/
```

### Rebuilding Docker after code changes

```bash
docker compose build --no-cache && docker compose up -d
```

Use `--no-cache` to ensure Python source changes aren't served from a stale layer.

---

## Tech Stack

| Layer | Library |
|---|---|
| UI | [Streamlit](https://streamlit.io) 1.55 |
| HTTP client | [httpx](https://www.python-httpx.org) (async) |
| Market data | [SerpAPI](https://serpapi.com) / Skroutz JSON |
| PDF parsing | [pdfplumber](https://github.com/jsvine/pdfplumber) |
| XLSX I/O | [openpyxl](https://openpyxl.readthedocs.io) |
| Charts | [Plotly](https://plotly.com/python/) |
| Containerisation | Docker + Compose |

---

## License

MIT — see [LICENSE](LICENSE) if present, otherwise use freely with attribution.
