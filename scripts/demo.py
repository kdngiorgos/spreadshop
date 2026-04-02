"""
Spreadshop — Demo / Proof-of-Concept Script
============================================
Parses all test supplier files, validates prices, runs analysis with
mock Skroutz data, and exports a sample XLSX report.

Run from the project root:
    python scripts/demo.py
"""
from __future__ import annotations
import io
import os
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from logger import setup_logging
from parsers.base import ParseError, ProductRecord, SkroutzResult, parse_file
from analysis.compare import analyze
from analysis.export import generate_xlsx
from config import PRICE_RATIO_MIN, PRICE_RATIO_MAX

setup_logging()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sep(char="─", width=80) -> None:
    print(char * width)


def header(title: str) -> None:
    sep()
    print(f"  {title}")
    sep()


def fmt_price(v: float) -> str:
    return f"€{v:7.2f}"


def fmt_ratio(wh: float, rt: float) -> str:
    ratio = wh / rt if rt else 0
    flag = "" if PRICE_RATIO_MIN <= ratio <= PRICE_RATIO_MAX else "  ⚠️ RATIO OUT OF RANGE"
    return f"{ratio:.3f}{flag}"


# ---------------------------------------------------------------------------
# Step 1 — Parse all test files
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent.parent

TEST_FILES = [
    DATA_DIR / "Atcare_Τιμοκατάλογος Συμπληρωμάτων Bio Tonics 2025.xlsx.xlsx",
    DATA_DIR / "Atcare_Τιμοκατάλογος Συμπληρωμάτων Bio Tonics 2025.xlsx.pdf",
    DATA_DIR / "VioGenesis Product List November 2025.xlsx.pdf",
]

header("STEP 1 — Parsing supplier files")

all_products: list[ProductRecord] = []
all_errors: list[ParseError] = []
parse_results: list[tuple] = []

for fp in TEST_FILES:
    if not fp.exists():
        print(f"  SKIP  {fp.name}  (file not found)")
        continue
    products, errors, warnings = parse_file(fp)
    all_products.extend(products)
    all_errors.extend(errors)
    for w in warnings:
        print(f"  ⚠️  {w}")
    status = "✅" if not errors else f"⚠️  {len(errors)} warn"
    parse_results.append((fp.name, products, errors, status))
    print(f"  {status}  {fp.suffix.upper()[1:]:4s}  {len(products):3d} products  {len(errors):2d} errors  │  {fp.name[:55]}")

sep()
print(f"  TOTAL  {len(all_products)} products  │  {len(all_errors)} parse errors")
sep()
print()

# Deduplicate by barcode (XLSX and PDF may overlap for Bio Tonics)
seen_barcodes: set[str] = set()
unique_products: list[ProductRecord] = []
for p in all_products:
    key = p.barcode if p.barcode else p.name
    if key not in seen_barcodes:
        seen_barcodes.add(key)
        unique_products.append(p)

print(f"  After deduplication: {len(unique_products)} unique products\n")

# ---------------------------------------------------------------------------
# Step 2 — Sample data per supplier
# ---------------------------------------------------------------------------
header("STEP 2 — Sample products (5 per supplier)")

suppliers = sorted({p.source for p in unique_products})
for supplier in suppliers:
    prods = [p for p in unique_products if p.source == supplier]
    print(f"\n  {supplier.upper()} — {len(prods)} products")
    print(f"  {'CODE':<10} {'PRODUCT':<45} {'WHSL':>8} {'RETL':>8} {'RATIO':>7}  {'CATEGORY'}")
    print(f"  {'-'*10} {'-'*45} {'-'*8} {'-'*8} {'-'*7}  {'-'*20}")
    for p in prods[:5]:
        print(
            f"  {p.code:<10} {p.name[:45]:<45} "
            f"{fmt_price(p.wholesale_price)} {fmt_price(p.retail_price)} "
            f"{fmt_ratio(p.wholesale_price, p.retail_price):>7}  {p.category[:20]}"
        )
    if len(prods) > 5:
        print(f"  ... and {len(prods) - 5} more")

print()

# ---------------------------------------------------------------------------
# Step 3 — Validate price ratios
# ---------------------------------------------------------------------------
header("STEP 3 — Price ratio validation")

ratio_issues = 0
for p in unique_products:
    if p.retail_price == 0:
        ratio_issues += 1
        continue
    ratio = p.wholesale_price / p.retail_price
    if not (PRICE_RATIO_MIN <= ratio <= PRICE_RATIO_MAX):
        ratio_issues += 1
        print(f"  ⚠️  {p.source:12s} | {p.name[:50]:50s} | wh={p.wholesale_price:.2f} rt={p.retail_price:.2f} ratio={ratio:.3f}")

if ratio_issues == 0:
    print(f"  ✅ All {len(unique_products)} products have valid wholesale/retail ratios ({PRICE_RATIO_MIN}–{PRICE_RATIO_MAX})")
else:
    print(f"\n  {ratio_issues} products with ratio issues (see above)")

print()

# ---------------------------------------------------------------------------
# Step 4 — Mock Skroutz data + Analysis
# ---------------------------------------------------------------------------
header("STEP 4 — Analysis (mock Skroutz data)")
print("  Using simulated Skroutz prices: retail × 0.85 as market low, 5 shops, 12 reviews")
print()

mock_results: dict[str, SkroutzResult] = {}
for i, p in enumerate(unique_products):
    key = p.barcode if p.barcode else p.name[:60].lower()
    # Simulate: 80% found, 20% not on Skroutz
    found = (i % 5) != 4
    mock_results[key] = SkroutzResult(
        found=found,
        product_name=p.name,
        product_url=f"https://www.skroutz.gr/s/mock/{i+1000}",
        lowest_price=round(p.retail_price * 0.85, 2) if found else 0.0,
        highest_price=round(p.retail_price * 1.05, 2) if found else 0.0,
        shop_count=5 if found else 0,
        rating=4.2 if found else 0.0,
        review_count=12 if found else 0,
        match_confidence=0.88 if found else 0.0,
        search_query=p.name,
    )

analyses = analyze(unique_products, mock_results)

found_count = sum(1 for a in analyses if a.skroutz.found)
strong_buy = sum(1 for a in analyses if a.recommendation == "strong_buy")
consider = sum(1 for a in analyses if a.recommendation == "consider")
skip = sum(1 for a in analyses if a.recommendation == "skip")
not_found = sum(1 for a in analyses if a.recommendation == "not_found")
avg_margin = sum(a.margin_pct for a in analyses if a.skroutz.found) / found_count if found_count else 0

print(f"  Products analyzed     : {len(analyses)}")
print(f"  Found on Skroutz      : {found_count}")
print(f"  Not on Skroutz        : {not_found}  (potential first-mover opportunities)")
print(f"  Avg gross margin      : {avg_margin:.1f}%")
print()
print(f"  Recommendations:")
print(f"    ✅ Strong Buy        : {strong_buy}")
print(f"    🟡 Consider         : {consider}")
print(f"    ❌ Skip              : {skip}")
print(f"    ⚪ Not Found         : {not_found}")
print()

print(f"  {'SCORE':>5}  {'MARGIN%':>8}  {'SHOPS':>5}  {'PRODUCT':<50}  {'REC'}")
print(f"  {'-'*5}  {'-'*8}  {'-'*5}  {'-'*50}  {'-'*12}")
for a in analyses[:10]:
    rec_short = {"strong_buy": "✅ Strong Buy", "consider": "🟡 Consider",
                 "skip": "❌ Skip", "not_found": "⚪ Not Found"}.get(a.recommendation, "")
    shops = str(a.skroutz.shop_count) if a.skroutz.found else "—"
    margin = f"{a.margin_pct:+.1f}%" if a.skroutz.found else "—"
    print(f"  {a.opportunity_score:5.1f}  {margin:>8}  {shops:>5}  {a.product.name[:50]:<50}  {rec_short}")

print()

# ---------------------------------------------------------------------------
# Step 5 — Export XLSX
# ---------------------------------------------------------------------------
header("STEP 5 — Export report")

reports_dir = Path(__file__).parent.parent / "reports"
reports_dir.mkdir(exist_ok=True)
report_path = reports_dir / "demo_report.xlsx"

xlsx_bytes = generate_xlsx(analyses, all_errors)
report_path.write_bytes(xlsx_bytes)

print(f"  ✅ Report saved: {report_path}")
print(f"     Size: {len(xlsx_bytes):,} bytes")
print(f"     Sheets: Opportunities · Not Found · Parse Errors")

print()
sep("═")
print(f"  ✅ DEMO COMPLETE")
print(f"     {len(unique_products)} unique products parsed across {len(suppliers)} supplier(s)")
print(f"     {len(all_errors)} parse error(s) total")
print(f"     Top recommendation: {analyses[0].product.name[:55]}")
print(f"     Report: {report_path}")
sep("═")
