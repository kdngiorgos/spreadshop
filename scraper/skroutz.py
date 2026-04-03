from __future__ import annotations
import difflib
import asyncio
import logging
import random
import re
import threading
import time
from typing import Callable, Optional, Dict, Any

import httpx

from parsers.base import ProductRecord, SkroutzResult
from config import (
    SCRAPER_DEFAULT_DELAY,
    SCRAPER_DEFAULT_JITTER,
    SCRAPER_FUZZY_MATCH_THRESHOLD,
    SCRAPER_PAGE_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.skroutz.gr"
_SEARCH_JSON_URL = "https://www.skroutz.gr/search.json"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def _price_from_text(text: str) -> Optional[float]:
    """Extract the first Euro price from arbitrary text."""
    if not text: return None
    text_no_dot = str(text).replace("\xa0", "").replace(".", "") # Remove thousands separator
    text_with_dot = str(text).replace("\xa0", "")

    # Path 1: comma decimal
    m = re.search(r"(\d+),(\d{2})", text_no_dot)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")

    # Fallback to dot decimal
    m = re.search(r"(\d+)\.(\d{2})", text_with_dot)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")

    return None

def _similarity(a: str, b: str) -> float:
    import difflib
    # Improved similarity logic to favor strings that start with the query
    a_lower = a.lower()
    b_lower = b.lower()

    # If the product name contains the query as a substring, boost its score proportionally
    boost = 0.0
    if a_lower in b_lower:
        # Boost proportional to how much of the target string the query covers
        boost = 0.5 * (len(a_lower) / max(1, len(b_lower)))

    return difflib.SequenceMatcher(None, a_lower, b_lower).ratio() + boost


# ---------------------------------------------------------------------------
# JSON parsing helpers (stateless — work on dicts)
# ---------------------------------------------------------------------------

def _parse_search_results_json(data: Dict[str, Any], query: str) -> Optional[SkroutzResult]:
    """Parse a Skroutz search JSON response and return the best match."""
    skus = data.get("skus", [])
    if not skus:
        logger.debug("No skus found for query %r in JSON response", query)
        return None

    best_result: Optional[SkroutzResult] = None
    best_score = 0.0

    for sku in skus[:10]:
        pname = sku.get("name", "")
        score = _similarity(query, pname)

        url = sku.get("sku_url", "")
        if url and not url.startswith("http"):
            url = _BASE_URL + url

        price_text = str(sku.get("price", ""))
        lowest = _price_from_text(price_text) or 0.0

        shop_count = sku.get("shop_count", 0)

        rating_str = str(sku.get("review_score", "0.0"))
        try:
            rating = float(rating_str.replace(",", "."))
        except (ValueError, AttributeError):
            rating = 0.0

        reviews = sku.get("reviews_count", 0)

        if score > best_score:
            best_score = score
            best_result = SkroutzResult(
                found=True,
                product_name=pname,
                product_url=url,
                lowest_price=lowest,
                highest_price=lowest,  # will be refined if we hit filter_products
                shop_count=shop_count,
                rating=rating,
                review_count=reviews,
                match_confidence=score,
                search_query=query,
            )
            # Store the sku id dynamically into the object so we can use it for filter_products.json
            setattr(best_result, "skroutz_id", sku.get("id"))

    if best_result and best_score >= SCRAPER_FUZZY_MATCH_THRESHOLD:
        return best_result

    return SkroutzResult(found=False, search_query=query)


# ---------------------------------------------------------------------------
# Main scraper class (uses HTTPX AsyncClient)
# ---------------------------------------------------------------------------

class SkroutzScraper:
    def __init__(
        self,
        headless: bool = False,
        delay: float = SCRAPER_DEFAULT_DELAY,
        delay_jitter: float = SCRAPER_DEFAULT_JITTER,
        on_status: Optional[Callable[[str], None]] = None,
        debug_dir: Optional[str] = None,
    ):
        self.headless = headless
        self.delay = delay
        self.delay_jitter = delay_jitter
        self.on_status = on_status or (lambda _: None)
        self.debug_dir = debug_dir

        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._stop = False
        self._tasks = []

    # ------------------------------------------------------------------
    def start(self) -> None:
        pass

    def stop(self) -> None:
        self._stop = True
        self._pause_event.set()  # unblock if currently paused
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def pause(self) -> None:
        self._pause_event.clear()  # block search() calls at the wait point
        logger.debug("Scraper paused")

    def resume(self) -> None:
        self._pause_event.set()   # unblock search() calls
        logger.debug("Scraper resumed")

    # ------------------------------------------------------------------
    def _wait_and_sleep(self) -> None:
        if self.delay <= 0:
            return
        jitter = random.uniform(-self.delay_jitter / 2, self.delay_jitter / 2)
        time.sleep(max(0.1, self.delay + jitter))

    def _save_debug(self, content: str, name: str) -> None:
        if not self.debug_dir:
            return
        import os
        os.makedirs(self.debug_dir, exist_ok=True)
        safe = re.sub(r"[^\w]", "_", name)[:40]
        path = os.path.join(self.debug_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------------
    def verify_selectors(self) -> tuple[bool, str]:
        """Quick health check — search a known product to validate JSON endpoints.

        Call after start() and before bulk scraping.  Returns (ok, message).
        """
        try:
            test_url = _SEARCH_JSON_URL
            self.on_status("Running endpoint health check…")

            with httpx.Client(headers={"User-Agent": _UA}) as client:
                resp = client.get(test_url, params={"keyphrase": "aspirin tablet"}, timeout=SCRAPER_PAGE_TIMEOUT_MS/1000.0)
                if resp.status_code != 200:
                    return False, f"Health check failed with status {resp.status_code}"

                data = resp.json()
                if "redirectUrl" in data:
                    return True, "Endpoints OK — redirectUrl found"
                elif "skus" in data:
                    return True, f"Endpoints OK — {len(data['skus'])} product(s) found"
                else:
                    return False, "Health check failed: Unrecognized JSON structure"

        except Exception as exc:
            logger.warning("Endpoint health check failed: %s", exc)
            return False, f"Health check error: {exc}"

    # ------------------------------------------------------------------
    async def _fetch_async(self, client: httpx.AsyncClient, query: str) -> Optional[Dict[str, Any]]:
        url = _SEARCH_JSON_URL
        try:
            resp = await client.get(url, params={"keyphrase": query}, timeout=SCRAPER_PAGE_TIMEOUT_MS/1000.0)
            if resp.status_code != 200:
                return None
            data = resp.json()

            # Check if it's a redirect to a product category JSON
            if "redirectUrl" in data:
                redirect_url = data["redirectUrl"]
                # Usually like: https://www.skroutz.gr/c/40/kinhta-thlefwna/.../Xiaomi-15.html?o=xiaomi15
                # We need to replace .html with .json
                if ".html" in redirect_url:
                    json_redirect_url = redirect_url.replace(".html", ".json")
                    if not json_redirect_url.startswith("http"):
                        json_redirect_url = _BASE_URL + json_redirect_url
                    resp2 = await client.get(json_redirect_url, timeout=SCRAPER_PAGE_TIMEOUT_MS/1000.0)
                    if resp2.status_code == 200:
                        return resp2.json()
            return data
        except Exception as e:
            logger.error("HTTP error fetching %s: %s", url, e)
            return None

    async def _fetch_filter_products_async(self, client: httpx.AsyncClient, skroutz_id: int) -> Optional[Dict[str, Any]]:
        url = f"https://www.skroutz.gr/s/{skroutz_id}/filter_products.json"
        try:
            resp = await client.get(url, timeout=SCRAPER_PAGE_TIMEOUT_MS/1000.0)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error("HTTP error fetching filter_products %s: %s", url, e)
            return None

    async def search_async(self, product: ProductRecord, client: httpx.AsyncClient) -> SkroutzResult:
        """Async Search for a product and return scraped Skroutz data."""
        # Check if paused (synchronously blocking is bad in async, but since this is
        # called in a bounded semaphore we can do a simple sleep loop)
        try:
            while not self._pause_event.is_set():
                if self._stop:
                    break
                await asyncio.sleep(0.5)

            if self._stop:
                return SkroutzResult(found=False, search_query=product.name)

            query = product.name
            self.on_status(f"Searching: {product.name[:60]}…")

            data = await self._fetch_async(client, query)
            if data:
                import json
                self._save_debug(json.dumps(data, indent=2), product.name)
                result = _parse_search_results_json(data, query)
            else:
                result = None

            if not result:
                result = SkroutzResult(found=False, search_query=query)

            # If not found by name and we have a barcode, retry with barcode
            if not result.found and product.barcode:
                if self._stop:
                    return SkroutzResult(found=False, search_query=product.name)
                await asyncio.sleep(self.delay + random.uniform(-self.delay_jitter/2, self.delay_jitter/2))
                self.on_status(f"Retrying by barcode: {product.barcode}")
                bc_data = await self._fetch_async(client, product.barcode)
                if bc_data:
                    bc_result = _parse_search_results_json(bc_data, product.barcode)
                    if bc_result and bc_result.found:
                        bc_result.search_query = query  # report original query
                        result = bc_result

            if result.found and hasattr(result, "skroutz_id") and getattr(result, "skroutz_id"):
                if self._stop:
                    return SkroutzResult(found=False, search_query=product.name)
                skroutz_id = getattr(result, "skroutz_id")
                await asyncio.sleep(self.delay + random.uniform(-self.delay_jitter/2, self.delay_jitter/2))
                filter_data = await self._fetch_filter_products_async(client, skroutz_id)
                if filter_data:
                    prices = []
                    product_cards = filter_data.get("product_cards", {})
                    for card_id, card_info in product_cards.items():
                        price = card_info.get("final_price") or _price_from_text(card_info.get("price", ""))
                        if price and 0.5 < price < 10000:
                            prices.append(price)
                    if prices:
                        result.lowest_price = min(prices)
                        result.highest_price = max(prices)

                    if "shop_count" in filter_data:
                        result.shop_count = filter_data["shop_count"]

            logger.debug(
                "Search result for %r: found=%s price=%.2f",
                product.name[:40], result.found, result.lowest_price,
            )

            await asyncio.sleep(self.delay + random.uniform(-self.delay_jitter/2, self.delay_jitter/2))
            return result
        except asyncio.CancelledError:
            self.on_status(f"Scraping cancelled for {product.name[:40]}")
            raise
        except Exception as exc:
            logger.error("Error scraping %r: %s", product.name[:40], exc)
            self.on_status(f"Error scraping {product.name[:40]}: {exc}")
            return SkroutzResult(found=False, search_query=product.name)

    async def bulk_search_async(self, products: list[ProductRecord], concurrency: int = 5) -> dict[str, SkroutzResult]:
        results = {}
        sem = asyncio.Semaphore(concurrency)
        self._tasks = []

        async with httpx.AsyncClient(headers={"User-Agent": _UA}, http2=True) as client:
            async def process_product(product: ProductRecord):
                async with sem:
                    res = await self.search_async(product, client)
                    results[product.barcode or product.name] = res

            for p in products:
                task = asyncio.create_task(process_product(p))
                self._tasks.append(task)

            await asyncio.gather(*self._tasks, return_exceptions=True)

        return results

    def search(self, product: ProductRecord) -> SkroutzResult:
        """Synchronous wrapper for search_async for backward compatibility."""
        import asyncio
        async def run_single():
            async with httpx.AsyncClient(headers={"User-Agent": _UA}, http2=True) as client:
                return await self.search_async(product, client)

        # If there's an existing loop, use it; otherwise run.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an already running loop we can't asyncio.run()
            # But search is meant to be called from a thread in Streamlit app.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, run_single()).result()
        else:
            return asyncio.run(run_single())
