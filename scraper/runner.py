"""Standalone scrape runner — no Streamlit dependency.

This module owns the end-to-end scraping flow so it can be called from:
  - app.py background thread (with UI callbacks)
  - scripts/scrape_cli.py (with stdout callbacks)
  - tests (with mock callbacks)

The caller supplies callbacks; this module writes nothing to global state.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from parsers.base import ProductRecord, SkroutzResult
from scraper.cache import ScrapeCache
from scraper import get_scraper
from config import (
    SCRAPER_CONCURRENCY,
    SCRAPER_DEFAULT_DELAY,
    SCRAPER_SOURCE,
    SERPAPI_KEY,
    CACHE_DIR,
    CACHE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)


def run_scrape(
    products: list[ProductRecord],
    api_key: str = SERPAPI_KEY,
    *,
    concurrency: int = SCRAPER_CONCURRENCY,
    delay: float = SCRAPER_DEFAULT_DELAY,
    source: str = SCRAPER_SOURCE,
    max_live_requests: int = 20,
    on_status: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    on_result: Callable[[str, SkroutzResult], None] = lambda key, r: None,
    on_scraper_ready: Callable = lambda s: None,
    stop_event: Optional[threading.Event] = None,
) -> dict[str, SkroutzResult]:
    """Scrape market data for a list of products.

    Runs synchronously (blocks). Designed to be called from a background
    thread or a CLI script.

    Args:
        products:        List of ProductRecord to search for.
        api_key:         API key for the chosen scraper source.
        concurrency:     Max parallel async workers.
        delay:           Base delay between requests (seconds).
        source:          Scraper backend: "serpapi" or "skroutz".
        on_status:       Called with human-readable status strings.
        on_progress:     Called with (done_count, total_count) after each item.
        on_result:       Called with (cache_key, SkroutzResult) as results arrive.
        on_scraper_ready: Called with the scraper instance once created — lets
                          callers wire up pause/resume/stop without tight coupling.
        max_live_requests: Cap on live API calls per run (cache hits don't count).
                           Prevents burning quota during testing. Default: 20.
        stop_event:      Set to signal an early stop.

    Returns:
        dict keyed by barcode (or name[:60].lower()) → SkroutzResult.
    """
    results: dict[str, SkroutzResult] = {}
    stop_event = stop_event or threading.Event()

    scraper = get_scraper(
        source,
        api_key=api_key,
        delay=delay,
        on_status=on_status,
        debug_dir="cache/debug",
    )
    on_scraper_ready(scraper)
    scraper.start()

    # Health check
    ok, hc_msg = scraper.verify_selectors()
    on_status(f"[{'OK' if ok else 'WARN'}] {hc_msg}")
    if not ok:
        on_status("[WARN] Proceeding — results may be incomplete.")

    total = len(products)
    done = 0
    cache = ScrapeCache(cache_dir=CACHE_DIR, ttl=CACHE_TTL_SECONDS)

    # Phase 1: serve from cache
    to_scrape: list[ProductRecord] = []
    for p in products:
        cached = cache.get(p.barcode, p.name)
        if cached is not None:
            key = p.barcode if p.barcode else p.name[:60].lower()
            results[key] = cached
            on_result(key, cached)
            done += 1
            on_progress(done, total)
            on_status(f"[cache] {p.name[:40]}")
        else:
            to_scrape.append(p)

    if not to_scrape:
        on_status("All products served from cache.")
        scraper.stop()
        return results

    # Apply live-request cap (cache hits already handled above)
    if max_live_requests and len(to_scrape) > max_live_requests:
        skipped = len(to_scrape) - max_live_requests
        on_status(f"[LIMIT] Capping live requests at {max_live_requests} (skipping {skipped} products).")
        to_scrape = to_scrape[:max_live_requests]

    on_status(f"Scraping {len(to_scrape)} products (concurrency={concurrency})…")

    # Phase 2: live scrape
    raw = asyncio.run(scraper.bulk_search_async(to_scrape, concurrency=concurrency))

    for p in to_scrape:
        if stop_event.is_set():
            on_status("Scraping stopped early.")
            break

        res_key = p.barcode or p.name
        key = p.barcode if p.barcode else p.name[:60].lower()
        result = raw.get(res_key) or SkroutzResult(found=False, search_query=p.name)

        results[key] = result
        on_result(key, result)
        cache.put(p.barcode, p.name, result)

        done += 1
        on_progress(done, total)

    scraper.stop()
    on_status(f"Done. {sum(1 for r in results.values() if r.found)}/{len(results)} found.")
    return results
