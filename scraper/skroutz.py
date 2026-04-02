from __future__ import annotations
import difflib
import logging
import random
import re
import threading
import time
from typing import Callable, Optional

from bs4 import BeautifulSoup

from parsers.base import ProductRecord, SkroutzResult
from config import (
    SCRAPER_DEFAULT_DELAY,
    SCRAPER_DEFAULT_JITTER,
    SCRAPER_FUZZY_MATCH_THRESHOLD,
    SCRAPER_PAGE_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.skroutz.gr"
_SEARCH_URL = "https://www.skroutz.gr/search?keyphrase={query}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# HTML parsing helpers (stateless — work on page source strings)
# ---------------------------------------------------------------------------

def _price_from_text(text: str) -> Optional[float]:
    """Extract the first Euro price from arbitrary text."""
    m = re.search(r"(\d{1,4})[,.](\d{2})\s*€", text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r"€\s*(\d{1,4})[,.](\d{2})", text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


def _int_from_text(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _parse_search_results(html: str, query: str) -> Optional[SkroutzResult]:
    """Parse a Skroutz search results page and return the best match."""
    soup = BeautifulSoup(html, "html.parser")

    # Check for "no results"
    no_res = soup.find(string=re.compile(r"δεν βρέθηκε|no results|0 αποτελέ", re.I))
    if no_res:
        return SkroutzResult(found=False, search_query=query)

    # Product cards are <li> elements within the results list
    # Skroutz uses various class names; look broadly.
    cards = soup.select("li[id^='sku-'], li.sku-item, .cf-item, li[class*='sku']")
    if not cards:
        # Broader fallback: any li with a price
        cards = soup.select("ul.cf li, #sku-list li")

    if not cards:
        logger.debug("No product cards found for query %r — HTML structure may have changed", query)
        return None  # Need to inspect HTML — caller should save for debugging

    best_result: Optional[SkroutzResult] = None
    best_score = 0.0

    for card in cards[:10]:
        # Product name
        name_el = card.select_one("a[class*='sku-link'], .sku-title a, h2 a, h3 a, .title a")
        if not name_el:
            continue
        pname = name_el.get_text(strip=True)
        score = _similarity(query, pname)

        # Product URL
        href = name_el.get("href", "")
        url = href if href.startswith("http") else _BASE_URL + href

        # Lowest price
        price_el = card.select_one("[class*='price'], .sku-price, .main-price")
        price_text = price_el.get_text(" ", strip=True) if price_el else ""
        lowest = _price_from_text(price_text) or 0.0

        # Shop count
        shops_el = card.select_one("[class*='shop'], [class*='store'], .shops-count")
        shops_text = shops_el.get_text(strip=True) if shops_el else card.get_text()
        shop_count = _int_from_text(shops_text, r"(\d+)\s*(?:καταστήμ|shop|store)")

        # Rating
        rating_el = card.select_one("[class*='rating'], [itemprop='ratingValue']")
        rating = 0.0
        if rating_el:
            rv = rating_el.get("content") or rating_el.get_text(strip=True)
            try:
                rating = float(rv.replace(",", "."))
            except (ValueError, AttributeError):
                pass

        review_el = card.select_one("[class*='review'], [itemprop='reviewCount']")
        reviews = 0
        if review_el:
            m = re.search(r"\d+", review_el.get_text())
            reviews = int(m.group()) if m else 0

        if score > best_score:
            best_score = score
            best_result = SkroutzResult(
                found=True,
                product_name=pname,
                product_url=url,
                lowest_price=lowest,
                highest_price=lowest,  # refined on product page if navigated
                shop_count=shop_count,
                rating=rating,
                review_count=reviews,
                match_confidence=score,
                search_query=query,
            )

    if best_result and best_score >= SCRAPER_FUZZY_MATCH_THRESHOLD:
        return best_result

    return SkroutzResult(found=False, search_query=query)


def _parse_product_page(html: str, query: str) -> SkroutzResult:
    """Parse a direct Skroutz product page (after redirect from search)."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ")

    # Product title
    title_el = (
        soup.select_one("h1[itemprop='name'], h1.sku-title, #sku-overview h1, h1")
    )
    pname = title_el.get_text(strip=True) if title_el else query

    # Prices — look for lowest price prominently displayed
    prices: list[float] = []
    for el in soup.select("[class*='price'], [itemprop='price'], .value"):
        p = _price_from_text(el.get_text(" ", strip=True))
        if p and 0.5 < p < 10000:
            prices.append(p)
    lowest = min(prices) if prices else 0.0
    highest = max(prices) if prices else 0.0

    # Shop count
    shop_count = _int_from_text(page_text, r"(\d+)\s*(?:καταστήμ|shop)")

    # Rating
    rating_el = soup.select_one("[itemprop='ratingValue']")
    rating = 0.0
    if rating_el:
        try:
            rating = float((rating_el.get("content") or rating_el.get_text()).replace(",", "."))
        except (ValueError, AttributeError):
            pass

    review_el = soup.select_one("[itemprop='reviewCount']")
    reviews = 0
    if review_el:
        m = re.search(r"\d+", review_el.get_text())
        reviews = int(m.group()) if m else 0

    return SkroutzResult(
        found=True,
        product_name=pname,
        product_url="",  # set by caller
        lowest_price=lowest,
        highest_price=highest,
        shop_count=shop_count,
        rating=rating,
        review_count=reviews,
        match_confidence=_similarity(query, pname),
        search_query=query,
    )


# ---------------------------------------------------------------------------
# Main scraper class (uses Playwright)
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
        self._browser = None
        self._page = None
        self._pw = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._stop = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        # Python 3.12+ on Windows uses ProactorEventLoop by default, which
        # Playwright's subprocess transport does not support.  Switch to
        # SelectorEventLoop and create a fresh one for this thread.
        import asyncio, sys
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())

        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
            ],
        )
        context = self._browser.new_context(
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            locale="el-GR",
            extra_http_headers={
                "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['el-GR', 'el', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)
        self._page = context.new_page()

        # Initial visit to establish session
        self.on_status("Opening Skroutz.gr…")
        self._page.goto("https://www.skroutz.gr", timeout=SCRAPER_PAGE_TIMEOUT_MS)
        self._accept_cookies()
        time.sleep(random.uniform(2.0, 4.0))

    def stop(self) -> None:
        self._stop = True
        self._pause_event.set()  # unblock if currently paused
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._browser = None
        self._page = None
        self._pw = None

    def pause(self) -> None:
        self._pause_event.clear()  # block search() calls at the wait point
        logger.debug("Scraper paused")

    def resume(self) -> None:
        self._pause_event.set()   # unblock search() calls
        logger.debug("Scraper resumed")

    # ------------------------------------------------------------------
    def _accept_cookies(self) -> None:
        try:
            btn = self._page.locator(
                "button:has-text('Αποδοχή'), button:has-text('Accept'), "
                "[id*='accept'], [class*='accept-all']"
            ).first
            if btn.is_visible(timeout=3000):
                btn.click()
                time.sleep(0.5)
        except Exception:
            pass

    def _wait_and_sleep(self) -> None:
        jitter = random.uniform(-self.delay_jitter / 2, self.delay_jitter / 2)
        time.sleep(max(1.0, self.delay + jitter))

    def _save_debug(self, html: str, name: str) -> None:
        if not self.debug_dir:
            return
        import os
        os.makedirs(self.debug_dir, exist_ok=True)
        safe = re.sub(r"[^\w]", "_", name)[:40]
        path = os.path.join(self.debug_dir, f"{safe}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    # ------------------------------------------------------------------
    def verify_selectors(self) -> tuple[bool, str]:
        """Quick health check — search a known product to validate HTML selectors.

        Call after start() and before bulk scraping.  Returns (ok, message).
        """
        if self._page is None:
            return False, "Scraper not started"
        try:
            test_url = _SEARCH_URL.format(query="aspirin+tablet")
            self.on_status("Running selector health check…")
            self._page.goto(test_url, timeout=SCRAPER_PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            try:
                self._page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            html = self._page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("li[id^='sku-'], li.sku-item, .cf-item, li[class*='sku']")
            if not cards:
                cards = soup.select("ul.cf li, #sku-list li")
            if cards:
                logger.info("Selector health check OK — %d cards found", len(cards))
                return True, f"Selectors OK — {len(cards)} product card(s) found on test page"
            # Check if it's a direct product page (also valid)
            if "/s/" in self._page.url:
                logger.info("Selector health check OK — direct product page redirect")
                return True, "Selectors OK — direct product page (test query redirected)"
            logger.warning("Selector health check: no product cards found")
            return False, (
                "No product cards found — Skroutz HTML structure may have changed. "
                "Scrape results may be incomplete."
            )
        except Exception as exc:
            logger.warning("Selector health check failed: %s", exc)
            return False, f"Health check error: {exc}"

    # ------------------------------------------------------------------
    def search(self, product: ProductRecord) -> SkroutzResult:
        """Search for a product and return scraped Skroutz data."""
        if self._page is None:
            raise RuntimeError("Scraper not started — call start() first")

        # Block here if paused; unblocks when resume() or stop() is called
        self._pause_event.wait()
        if self._stop:
            return SkroutzResult(found=False, search_query=product.name)

        # Primary query: product name
        query = product.name
        url = _SEARCH_URL.format(query=query.replace(" ", "+"))
        self.on_status(f"Searching: {product.name[:60]}…")

        try:
            self._page.goto(url, timeout=SCRAPER_PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            try:
                self._page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass  # continue if networkidle times out (background polling, etc.)

            current_url = self._page.url
            html = self._page.content()

            # Check if we landed on a product page (direct match redirect)
            if "/s/" in current_url and "search" not in current_url:
                result = _parse_product_page(html, query)
                result.product_url = current_url
            else:
                self._save_debug(html, product.name)
                result = _parse_search_results(html, query)
                if result is None:
                    # Unknown page structure — save HTML and return not-found
                    result = SkroutzResult(found=False, search_query=query)

            # If not found by name and we have a barcode, retry with barcode
            if not result.found and product.barcode:
                self._wait_and_sleep()
                bc_url = _SEARCH_URL.format(query=product.barcode)
                self.on_status(f"Retrying by barcode: {product.barcode}")
                self._page.goto(bc_url, timeout=SCRAPER_PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                try:
                    self._page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
                html2 = self._page.content()
                bc_result = _parse_search_results(html2, product.barcode)
                if bc_result and bc_result.found:
                    bc_result.search_query = query  # report original query
                    result = bc_result

            logger.debug(
                "Search result for %r: found=%s price=%.2f",
                product.name[:40], result.found, result.lowest_price,
            )

        except Exception as exc:
            logger.error("Error scraping %r: %s", product.name[:40], exc)
            self.on_status(f"Error scraping {product.name[:40]}: {exc}")
            result = SkroutzResult(found=False, search_query=query)

        self._wait_and_sleep()
        return result
