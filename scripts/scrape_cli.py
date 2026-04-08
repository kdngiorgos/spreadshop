"""Standalone scraper CLI — test market data without launching Streamlit.

Usage:
    python scripts/scrape_cli.py                     # scrape all supplier files
    python scripts/scrape_cli.py --limit 5           # first 5 products only
    python scripts/scrape_cli.py --product "Vitamin" # products whose name contains this

Examples:
    python scripts/scrape_cli.py --limit 3
    python scripts/scrape_cli.py --product "ginseng" --limit 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path when run from any directory
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from parsers.base import parse_file
from scraper.runner import run_scrape
from config import SERPAPI_KEY


def _find_supplier_files() -> list[Path]:
    exts = {".xlsx", ".pdf"}
    return sorted(
        p for p in ROOT.iterdir()
        if p.suffix.lower() in exts and not p.name.startswith(".")
    )


def _load_products(files: list[Path]) -> list:
    products = []
    seen_barcodes: set[str] = set()
    for f in files:
        try:
            prods, errors, warnings = parse_file(f)
            for w in warnings:
                print(f"[WARN] {w}")
            for p in prods:
                key = p.barcode or p.name
                if key not in seen_barcodes:
                    seen_barcodes.add(key)
                    products.append(p)
            print(f"  {f.name}: {len(prods)} products, {len(errors)} errors")
        except Exception as exc:
            print(f"  [ERROR] {f.name}: {exc}")
    return products


def _print_table(results: dict, products_by_key: dict) -> None:
    header = f"{'PRODUCT':<45} {'WHOLESALE':>10} {'MARKET':>10} {'MARGIN':>8} {'SHOPS':>6}"
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    found = [(k, r) for k, r in results.items() if r.found]
    not_found = [(k, r) for k, r in results.items() if not r.found]

    for key, result in sorted(found, key=lambda x: -(x[1].lowest_price or 0)):
        p = products_by_key.get(key)
        name = (p.name if p else result.product_name)[:44]
        wh = p.wholesale_price if p else 0.0
        market = result.lowest_price
        margin = ((market - wh) / wh * 100) if wh else 0
        print(f"{name:<45} {wh:>10.2f} {market:>10.2f} {margin:>7.1f}% {result.shop_count:>6}")

    if not_found:
        print(f"\nNot found on market: {len(not_found)} products")
        for key, _ in not_found[:5]:
            p = products_by_key.get(key)
            print(f"  - {(p.name if p else key)[:60]}")
        if len(not_found) > 5:
            print(f"  ... and {len(not_found) - 5} more")

    print("=" * len(header))
    print(f"Total: {len(results)} | Found: {len(found)} | Not found: {len(not_found)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape market prices for supplier products")
    parser.add_argument("--limit", type=int, default=None, help="Max products to scrape")
    parser.add_argument("--product", type=str, default=None, help="Filter products by name (case-insensitive)")
    parser.add_argument("--api-key", type=str, default=SERPAPI_KEY, help="SerpAPI key (default: from .env)")
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] No SerpAPI key found. Set SERPAPI_KEY in .env or pass --api-key.")
        return 1

    # Load products
    files = _find_supplier_files()
    if not files:
        print("[ERROR] No supplier files (.xlsx/.pdf) found in project root.")
        return 1

    print(f"Loading {len(files)} supplier file(s)…")
    all_products = _load_products(files)
    print(f"Total unique products: {len(all_products)}")

    # Filter / limit
    if args.product:
        needle = args.product.lower()
        all_products = [p for p in all_products if needle in p.name.lower()]
        print(f"Filtered to {len(all_products)} products matching {args.product!r}")

    if args.limit:
        all_products = all_products[:args.limit]
        print(f"Limited to first {len(all_products)} products")

    if not all_products:
        print("No products to scrape.")
        return 1

    # Build lookup for the summary table
    products_by_key = {
        (p.barcode if p.barcode else p.name[:60].lower()): p
        for p in all_products
    }

    # Run scrape
    print(f"\nScraping {len(all_products)} product(s)…\n")
    results = run_scrape(
        all_products,
        api_key=args.api_key,
        on_status=lambda msg: print(f"  {msg}"),
        on_progress=lambda done, total: print(f"  [{done}/{total}]") if done % 5 == 0 else None,
    )

    _print_table(results, products_by_key)

    return 0 if any(r.found for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
