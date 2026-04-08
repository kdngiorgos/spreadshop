"""SerpAPI Google Shopping scraper — drop-in replacement for SkroutzScraper.

Returns SkroutzResult objects with identical schema so the rest of the app
(app.py, analysis/compare.py, analysis/export.py) requires zero changes.

Popularity signal:
  shop_count = number of distinct .gr-domain sources in Shopping results.
  This is a better Greek-market signal than raw Skroutz shop_count.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import random
import re
from typing import Callable, Optional

import httpx

from parsers.base import ProductRecord, SkroutzResult
from scraper.cache import ScrapeCache
from config import (
    SCRAPER_DEFAULT_DELAY,
    SCRAPER_DEFAULT_JITTER,
    SCRAPER_FUZZY_MATCH_THRESHOLD,
    SCRAPER_PAGE_TIMEOUT_MS,
    SCRAPER_MAX_RETRIES,
    CACHE_TTL_SECONDS,
    CACHE_DIR,
)

logger = logging.getLogger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"


# ---------------------------------------------------------------------------
# Helpers (mirrors of skroutz.py helpers — kept local to avoid coupling)
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    a_lower = a.lower()
    b_lower = b.lower()
    boost = 0.0
    if a_lower in b_lower:
        boost = 0.5 * (len(a_lower) / max(1, len(b_lower)))
    return difflib.SequenceMatcher(None, a_lower, b_lower).ratio() + boost


def _extract_price(value) -> float:
    """Return float price from extracted_price field (already a number) or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _greek_shop_count(results: list[dict]) -> int:
    """Count distinct .gr domain sources — proxy for Greek market penetration."""
    sources = {r.get("source", "") for r in results if ".gr" in r.get("source", "").lower()}
    return len(sources)


# ---------------------------------------------------------------------------
# SerpApiScraper
# ---------------------------------------------------------------------------

class SerpApiScraper:
    def __init__(
        self,
        api_key: str,
        delay: float = SCRAPER_DEFAULT_DELAY,
        delay_jitter: float = SCRAPER_DEFAULT_JITTER,
        on_status: Optional[Callable[[str], None]] = None,
        debug_dir: Optional[str] = None,
        headless: bool = False,  # ignored — kept for interface compatibility
    ):
        if not api_key:
            raise ValueError("SerpAPI key is required. Set SERPAPI_KEY env var or enter it in the UI.")
        self.api_key = api_key
        self.delay = delay
        self.delay_jitter = delay_jitter
        self.on_status = on_status or (lambda _: None)
        self.debug_dir = debug_dir

        self._cache = ScrapeCache(cache_dir=CACHE_DIR, ttl=CACHE_TTL_SECONDS)
        self._paused = False
        self._stop = False
        self._tasks: list = []

    # ------------------------------------------------------------------
    # Pause / resume / stop (same interface as SkroutzScraper)
    # ------------------------------------------------------------------

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self._stop = True
        self._paused = False
        for task in self._tasks:
            if not task.done():
                try:
                    task.get_loop().call_soon_threadsafe(task.cancel)
                except Exception:
                    pass

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def verify_selectors(self) -> tuple[bool, str]:
        """Verify API key with a test query."""
        self.on_status("Checking SerpAPI key…")
        try:
            resp = httpx.get(
                _SERPAPI_URL,
                params={"engine": "google_shopping", "q": "vitamin c", "hl": "el", "gl": "gr",
                        "api_key": self.api_key, "num": 3},
                timeout=SCRAPER_PAGE_TIMEOUT_MS / 1000.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                n = len(data.get("shopping_results", []))
                return True, f"SerpAPI OK — {n} result(s) for test query"
            elif resp.status_code == 401:
                return False, "Invalid SerpAPI key (401 Unauthorized)"
            else:
                return False, f"SerpAPI returned HTTP {resp.status_code}"
        except Exception as exc:
            return False, f"SerpAPI health check error: {exc}"

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def _jitter_delay(self) -> float:
        return max(0.05, self.delay + random.uniform(-self.delay_jitter / 2, self.delay_jitter / 2))

    async def _fetch_async(self, client: httpx.AsyncClient, query: str) -> Optional[list[dict]]:
        """Fetch Google Shopping results for query. Returns shopping_results list or None."""
        params = {
            "engine": "google_shopping",
            "q": query,
            "hl": "el",
            "gl": "gr",
            "api_key": self.api_key,
            "num": 10,
        }
        for attempt in range(SCRAPER_MAX_RETRIES):
            try:
                logger.info("→ SerpAPI q=%r (attempt %d)", query, attempt + 1)
                resp = await client.get(_SERPAPI_URL, params=params, timeout=SCRAPER_PAGE_TIMEOUT_MS / 1000.0)
                logger.info("← HTTP %d", resp.status_code)
            except Exception as exc:
                logger.error("SerpAPI request error: %s", exc)
                return None

            if resp.status_code == 200:
                data = resp.json()
                return data.get("shopping_results", [])

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("SerpAPI rate-limited, waiting %ds", wait)
                await asyncio.sleep(wait)
                continue

            logger.warning("SerpAPI HTTP %d for query %r — not retrying", resp.status_code, query)
            return None

        return None

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def _parse_results(self, results: list[dict], query: str, barcode_mode: bool = False) -> SkroutzResult:
        if not results:
            return SkroutzResult(found=False, search_query=query)

        best: Optional[dict] = None
        best_score = 0.0

        for r in results[:10]:
            title = r.get("title", "")
            score = 1.0 if barcode_mode else _similarity(query, title)
            if score > best_score:
                best_score = score
                best = r

        if best is None or best_score < SCRAPER_FUZZY_MATCH_THRESHOLD:
            return SkroutzResult(found=False, search_query=query)

        prices = [_extract_price(r.get("extracted_price")) for r in results if r.get("extracted_price")]
        lowest = min(prices) if prices else _extract_price(best.get("extracted_price"))
        highest = max(prices) if prices else lowest

        shop_count = _greek_shop_count(results)

        rating_raw = best.get("rating", 0.0)
        try:
            rating = float(str(rating_raw).replace(",", "."))
        except (ValueError, TypeError):
            rating = 0.0

        reviews = best.get("reviews", 0) or 0

        return SkroutzResult(
            found=True,
            product_name=best.get("title", ""),
            product_url=best.get("link", ""),
            lowest_price=round(lowest, 2),
            highest_price=round(highest, 2),
            shop_count=shop_count,
            rating=rating,
            review_count=int(reviews),
            match_confidence=round(best_score, 3),
            search_query=query,
            skroutz_id=None,
        )

    # ------------------------------------------------------------------
    # Search single product
    # ------------------------------------------------------------------

    async def search_async(self, product: ProductRecord, client: httpx.AsyncClient) -> SkroutzResult:
        # 1. Check cache
        cached = self._cache.get(product.barcode, product.name)
        if cached is not None:
            self.on_status(f"[cache] {product.name[:40]}")
            return cached

        if self._stop:
            return SkroutzResult(found=False, search_query=product.name)

        while self._paused:
            await asyncio.sleep(0.5)

        await asyncio.sleep(self._jitter_delay())

        # 2. Search by name
        self.on_status(f"Searching: {product.name[:40]}")
        results = await self._fetch_async(client, product.name)
        result = self._parse_results(results or [], product.name)

        # 3. Fallback: search by barcode
        if not result.found and product.barcode:
            self.on_status(f"Barcode fallback: {product.barcode}")
            results = await self._fetch_async(client, product.barcode)
            result = self._parse_results(results or [], product.barcode, barcode_mode=True)

        if result.found:
            self.on_status(f"Found: {result.product_name[:40]} @ €{result.lowest_price:.2f}")
        else:
            self.on_status(f"Not found: {product.name[:40]}")

        self._cache.put(product.barcode, product.name, result)
        return result

    # ------------------------------------------------------------------
    # Bulk search (same signature as SkroutzScraper.bulk_search_async)
    # ------------------------------------------------------------------

    async def bulk_search_async(
        self, products: list[ProductRecord], concurrency: int = 5
    ) -> dict[str, SkroutzResult]:
        results: dict[str, SkroutzResult] = {}
        sem = asyncio.Semaphore(concurrency)
        self._tasks = []

        async with httpx.AsyncClient() as client:
            async def process(product: ProductRecord):
                async with sem:
                    res = await self.search_async(product, client)
                    results[product.barcode or product.name] = res

            for p in products:
                task = asyncio.create_task(process(p))
                self._tasks.append(task)

            await asyncio.gather(*self._tasks, return_exceptions=True)

        return results

    def search(self, product: ProductRecord) -> SkroutzResult:
        """Synchronous wrapper — used in tests and scripts."""
        async def _run():
            async with httpx.AsyncClient() as client:
                return await self.search_async(product, client)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            return asyncio.run(_run())
