from __future__ import annotations
import difflib
import asyncio
import logging
import random
import re
import threading
import time
from typing import Callable, Optional, Dict, Any

from curl_cffi.requests import AsyncSession, Session

from parsers.base import ProductRecord, SkroutzResult
from config import (
    SCRAPER_DEFAULT_DELAY,
    SCRAPER_DEFAULT_JITTER,
    SCRAPER_FUZZY_MATCH_THRESHOLD,
    SCRAPER_MAX_RETRIES,
    SCRAPER_PAGE_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.skroutz.gr"
_SEARCH_JSON_URL = "https://www.skroutz.gr/search.json"

# curl-cffi impersonate="chrome124" handles UA, Accept, Accept-Language,
# sec-ch-ua, HTTP/2, and the TLS fingerprint automatically.
# Only add headers that are specific to our request context.
_HEADERS = {
    "Referer": "https://www.skroutz.gr/",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


# ---------------------------------------------------------------------------
# Price / similarity helpers (stateless)
# ---------------------------------------------------------------------------

def _price_from_text(text: str) -> Optional[float]:
    """Extract the first Euro price from arbitrary text."""
    if not text:
        return None
    text_no_dot = str(text).replace("\xa0", "").replace(".", "")  # strip thousands sep
    text_with_dot = str(text).replace("\xa0", "")

    m = re.search(r"(\d+),(\d{2})", text_no_dot)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")

    m = re.search(r"(\d+)\.(\d{2})", text_with_dot)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")

    return None


def _similarity(a: str, b: str) -> float:
    a_lower = a.lower()
    b_lower = b.lower()
    boost = 0.0
    if a_lower in b_lower:
        boost = 0.5 * (len(a_lower) / max(1, len(b_lower)))
    return difflib.SequenceMatcher(None, a_lower, b_lower).ratio() + boost


# ---------------------------------------------------------------------------
# JSON parsing helpers (stateless — work on dicts)
# ---------------------------------------------------------------------------

def _parse_search_results_json(data: Dict[str, Any], query: str, barcode_mode: bool = False) -> Optional[SkroutzResult]:
    """Parse a Skroutz search JSON response and return the best match."""
    skus = data.get("skus", [])
    if not skus:
        logger.debug("No skus found for query %r in JSON response", query)
        return None

    best_result: Optional[SkroutzResult] = None
    best_score = 0.0

    for sku in skus[:10]:
        pname = sku.get("name", "")
        score = 1.0 if barcode_mode else _similarity(query, pname)

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
                highest_price=lowest,
                shop_count=shop_count,
                rating=rating,
                review_count=reviews,
                match_confidence=score,
                search_query=query,
                skroutz_id=sku.get("id"),
            )

        if barcode_mode:
            break

    if best_result and best_score >= SCRAPER_FUZZY_MATCH_THRESHOLD:
        return best_result

    return SkroutzResult(found=False, search_query=query)


# ---------------------------------------------------------------------------
# Main scraper class (uses curl-cffi AsyncSession — Chrome TLS impersonation)
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
        self._pause_event.set()
        self._stop = False
        self._tasks = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self._stop = True
        self._pause_event.set()
        for task in self._tasks:
            if not task.done():
                try:
                    task.get_loop().call_soon_threadsafe(task.cancel)
                except Exception:
                    pass

    def pause(self) -> None:
        self._pause_event.clear()
        logger.debug("Scraper paused")

    def resume(self) -> None:
        self._pause_event.set()
        logger.debug("Scraper resumed")

    # ------------------------------------------------------------------
    def _jitter_delay(self) -> float:
        return max(0.1, self.delay + random.uniform(-self.delay_jitter / 2, self.delay_jitter / 2))

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
        """Health check — hits the JSON endpoint with a test query."""
        try:
            self.on_status("Running endpoint health check…")
            with Session(impersonate="chrome124") as client:
                logger.info("→ GET %s (health check)", _SEARCH_JSON_URL)
                resp = client.get(
                    _SEARCH_JSON_URL,
                    params={"keyphrase": "aspirin tablet"},
                    headers=_HEADERS,
                    timeout=SCRAPER_PAGE_TIMEOUT_MS / 1000.0,
                )
                logger.info("← HTTP %d %s", resp.status_code, resp.url)
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
    async def _fetch_async(self, client: AsyncSession, query: str) -> Optional[Dict[str, Any]]:
        url = _SEARCH_JSON_URL
        timeout = SCRAPER_PAGE_TIMEOUT_MS / 1000.0

        for attempt in range(SCRAPER_MAX_RETRIES):
            try:
                logger.info("→ GET %s keyphrase=%r", url, query)
                resp = await client.get(url, params={"keyphrase": query}, headers=_HEADERS, timeout=timeout)
                logger.info("← HTTP %d %s", resp.status_code, resp.url)
            except Exception as e:
                logger.error("HTTP error fetching %s: %s", url, e)
                return None

            if resp.status_code == 200:
                data = resp.json()
                if "redirectUrl" in data:
                    redirect_url = data["redirectUrl"]
                    if ".html" in redirect_url:
                        json_redirect_url = redirect_url.replace(".html", ".json")
                        if not json_redirect_url.startswith("http"):
                            json_redirect_url = _BASE_URL + json_redirect_url
                        try:
                            logger.info("→ GET %s (redirect follow)", json_redirect_url)
                            resp2 = await client.get(json_redirect_url, headers=_HEADERS, timeout=timeout)
                            logger.info("← HTTP %d %s", resp2.status_code, resp2.url)
                            if resp2.status_code == 200:
                                return resp2.json()
                        except Exception as e:
                            logger.error("HTTP error following redirect %s: %s", json_redirect_url, e)
                return data

            if resp.status_code in (429, 503):
                retry_after = resp.headers.get("Retry-After", "")
                backoff = int(retry_after) if retry_after.isdigit() else (2 ** attempt) * 10
                logger.warning(
                    "HTTP %d — backing off %ds (attempt %d/%d) for query %r",
                    resp.status_code, backoff, attempt + 1, SCRAPER_MAX_RETRIES, query,
                )
                self.on_status(f"Rate limited — waiting {backoff}s before retry…")
                await asyncio.sleep(backoff)
                continue

            logger.warning("HTTP %d for query %r — not retrying", resp.status_code, query)
            return None

        logger.error("Giving up on query %r after %d attempts", query, SCRAPER_MAX_RETRIES)
        return None

    async def _fetch_filter_products_async(
        self, client: AsyncSession, skroutz_id: int, product_url: str = ""
    ) -> Optional[Dict[str, Any]]:
        url = f"https://www.skroutz.gr/s/{skroutz_id}/filter_products.json"
        referer = product_url or f"https://www.skroutz.gr/s/{skroutz_id}"
        timeout = SCRAPER_PAGE_TIMEOUT_MS / 1000.0
        headers = {**_HEADERS, "Referer": referer}

        for attempt in range(SCRAPER_MAX_RETRIES):
            try:
                logger.info("→ GET %s (filter_products)", url)
                resp = await client.get(url, headers=headers, timeout=timeout)
                logger.info("← HTTP %d %s", resp.status_code, resp.url)
            except Exception as e:
                logger.error("HTTP error fetching filter_products %s: %s", url, e)
                return None

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in (429, 503):
                retry_after = resp.headers.get("Retry-After", "")
                backoff = int(retry_after) if retry_after.isdigit() else (2 ** attempt) * 10
                logger.warning(
                    "HTTP %d on filter_products — backing off %ds (attempt %d/%d)",
                    resp.status_code, backoff, attempt + 1, SCRAPER_MAX_RETRIES,
                )
                self.on_status(f"Rate limited — waiting {backoff}s before retry…")
                await asyncio.sleep(backoff)
                continue

            logger.warning("filter_products returned HTTP %d for SKU %s", resp.status_code, skroutz_id)
            return None

        logger.error("Giving up on filter_products for SKU %s after %d attempts", skroutz_id, SCRAPER_MAX_RETRIES)
        return None

    async def _warmup_session(self, client: AsyncSession) -> None:
        """Visit the homepage to establish session cookies."""
        try:
            self.on_status("Establishing Skroutz session…")
            logger.info("→ GET %s (session warmup)", _BASE_URL)
            resp = await client.get(_BASE_URL, timeout=15.0)
            logger.info("← HTTP %d %s (warmup)", resp.status_code, resp.url)
        except Exception as exc:
            logger.warning("Session warmup failed (will try anyway): %s", exc)

    async def search_async(self, product: ProductRecord, client: AsyncSession) -> SkroutzResult:
        """Search for a single product asynchronously."""
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

            if not result.found and product.barcode:
                if self._stop:
                    return SkroutzResult(found=False, search_query=product.name)
                await asyncio.sleep(self._jitter_delay())
                self.on_status(f"Retrying by barcode: {product.barcode}")
                bc_data = await self._fetch_async(client, product.barcode)
                if bc_data:
                    bc_result = _parse_search_results_json(bc_data, product.barcode, barcode_mode=True)
                    if bc_result and bc_result.found:
                        bc_result.search_query = query
                        result = bc_result

            if result.found and result.skroutz_id:
                if self._stop:
                    return SkroutzResult(found=False, search_query=product.name)
                await asyncio.sleep(self._jitter_delay())
                filter_data = await self._fetch_filter_products_async(client, result.skroutz_id, result.product_url)
                if filter_data:
                    prices = []
                    for _card_id, card_info in filter_data.get("product_cards", {}).items():
                        price = card_info.get("final_price") or _price_from_text(card_info.get("price", ""))
                        if price and 0.5 < price < 10000:
                            prices.append(price)
                    if prices:
                        result.lowest_price = min(prices)
                        result.highest_price = max(prices)
                    if "shop_count" in filter_data:
                        result.shop_count = filter_data["shop_count"]

            logger.debug("Result for %r: found=%s price=%.2f", product.name[:40], result.found, result.lowest_price)
            await asyncio.sleep(self._jitter_delay())
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

        async with AsyncSession(impersonate="chrome124") as client:
            await self._warmup_session(client)

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
        """Synchronous wrapper around search_async (backward compatibility)."""
        async def run_single():
            async with AsyncSession(impersonate="chrome124") as client:
                await self._warmup_session(client)
                return await self.search_async(product, client)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, run_single()).result()
        else:
            return asyncio.run(run_single())
