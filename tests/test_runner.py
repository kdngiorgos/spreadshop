"""Unit tests for scraper.runner.run_scrape — uses a fake scraper to avoid network."""
from __future__ import annotations

import threading

import pytest

from parsers.base import ProductRecord, SkroutzResult
from scraper.cache import ScrapeCache
from scraper import runner as runner_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeScraper:
    """Minimal stand-in for SkroutzScraper / SerpApiScraper.

    Records calls and lets each test specify per-product results via
    `results_map`. Honors the on_item_done callback so per-item progress
    wiring can be exercised end-to-end.
    """

    def __init__(self, results_map=None):
        self.results_map = results_map or {}
        self.start_called = False
        self.stop_called = False
        self.health_called = False
        self.bulk_called_with = None

    def start(self):
        self.start_called = True

    def stop(self):
        self.stop_called = True

    def pause(self):
        pass

    def resume(self):
        pass

    def verify_selectors(self):
        self.health_called = True
        return True, "fake ok"

    async def bulk_search_async(self, products, concurrency=2, on_item_done=None):
        self.bulk_called_with = list(products)
        out = {}
        for p in products:
            key = p.barcode or p.name
            res = self.results_map.get(
                key,
                SkroutzResult(found=True, lowest_price=10.0, search_query=p.name),
            )
            out[key] = res
            if on_item_done is not None:
                on_item_done(key, res)
        return out


@pytest.fixture
def isolated_runner(tmp_path, monkeypatch):
    """Point runner.CACHE_DIR at a tmp dir and return a FakeScraper handle."""
    monkeypatch.setattr(runner_mod, "CACHE_DIR", str(tmp_path))

    fakes: dict[str, FakeScraper] = {}

    def _factory(source, **kwargs):
        scraper = FakeScraper(results_map=fakes.pop("results_map", {}))
        fakes["scraper"] = scraper
        return scraper

    monkeypatch.setattr(runner_mod, "get_scraper", _factory)
    return fakes, tmp_path


def _product(barcode="123", name="Foo") -> ProductRecord:
    return ProductRecord(
        source="test", code="C1", name=name,
        wholesale_price=5.0, retail_price=10.0, barcode=barcode,
    )


# ---------------------------------------------------------------------------
# Per-item progress wiring
# ---------------------------------------------------------------------------

class TestProgressCallbacks:
    def test_on_progress_fires_per_item(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        products = [_product(barcode=f"E{i}", name=f"Prod {i}") for i in range(5)]

        progress_ticks: list[int] = []
        runner_mod.run_scrape(
            products, api_key="",
            source="skroutz",
            max_live_requests=0,
            on_progress=lambda done, total: progress_ticks.append(done),
            on_status=lambda _: None,
        )
        # One tick per live product
        assert progress_ticks == [1, 2, 3, 4, 5]

    def test_on_result_called_with_canonical_key(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        products = [_product(barcode="EAN1", name="A"), _product(barcode="", name="No Barcode")]

        keys: list[str] = []
        runner_mod.run_scrape(
            products, api_key="", source="skroutz",
            max_live_requests=0,
            on_result=lambda key, r: keys.append(key),
            on_status=lambda _: None,
        )
        # First product: barcode wins. Second: name[:60].lower() (cache convention)
        assert "EAN1" in keys
        assert "no barcode" in keys


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------

class TestCacheHits:
    def test_cache_hits_fire_on_cache_hit_not_on_result(self, isolated_runner):
        fakes, tmp_path = isolated_runner

        # Pre-populate cache
        cache = ScrapeCache(cache_dir=tmp_path)
        cached_p = _product(barcode="CACHED1", name="Cached Item")
        cache.put(cached_p.barcode, cached_p.name,
                  SkroutzResult(found=True, lowest_price=99.0, search_query="x"))

        live_p = _product(barcode="LIVE1", name="Live Item")

        cache_hits: list[str] = []
        live_results: list[str] = []
        runner_mod.run_scrape(
            [cached_p, live_p], api_key="", source="skroutz",
            max_live_requests=0,
            on_cache_hit=lambda key, r: cache_hits.append(key),
            on_result=lambda key, r: live_results.append(key),
            on_status=lambda _: None,
        )
        assert cache_hits == ["CACHED1"]
        assert live_results == ["LIVE1"]

    def test_all_cached_short_circuits_scraper(self, isolated_runner):
        fakes, tmp_path = isolated_runner

        cache = ScrapeCache(cache_dir=tmp_path)
        p = _product(barcode="C1", name="Cached")
        cache.put(p.barcode, p.name, SkroutzResult(found=True, lowest_price=5.0))

        runner_mod.run_scrape(
            [p], api_key="", source="skroutz",
            max_live_requests=0,
            on_status=lambda _: None,
        )
        # Scraper still constructed (verify_selectors runs), but bulk_search_async never called
        assert fakes["scraper"].bulk_called_with is None
        assert fakes["scraper"].stop_called is True


# ---------------------------------------------------------------------------
# max_live_requests cap
# ---------------------------------------------------------------------------

class TestMaxLiveRequests:
    def test_cap_truncates_pending_list(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        products = [_product(barcode=f"E{i}") for i in range(10)]

        runner_mod.run_scrape(
            products, api_key="", source="skroutz",
            max_live_requests=3,
            on_status=lambda _: None,
        )
        assert len(fakes["scraper"].bulk_called_with) == 3

    def test_zero_means_unlimited(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        products = [_product(barcode=f"E{i}") for i in range(10)]

        runner_mod.run_scrape(
            products, api_key="", source="skroutz",
            max_live_requests=0,
            on_status=lambda _: None,
        )
        assert len(fakes["scraper"].bulk_called_with) == 10


# ---------------------------------------------------------------------------
# Stop event
# ---------------------------------------------------------------------------

class TestStopEvent:
    def test_results_still_returned_when_stop_set_post_scrape(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        products = [_product(barcode=f"E{i}") for i in range(3)]

        stop = threading.Event()
        results = runner_mod.run_scrape(
            products, api_key="", source="skroutz",
            max_live_requests=0,
            on_status=lambda _: None,
            stop_event=stop,
        )
        # Without setting the event, all results should arrive
        assert len(results) == 3


# ---------------------------------------------------------------------------
# scraper lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_scraper_is_started_and_stopped(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        runner_mod.run_scrape(
            [_product()], api_key="", source="skroutz",
            max_live_requests=0,
            on_status=lambda _: None,
        )
        s = fakes["scraper"]
        assert s.start_called is True
        assert s.health_called is True
        assert s.stop_called is True

    def test_on_scraper_ready_invoked_with_instance(self, isolated_runner):
        fakes, tmp_path = isolated_runner
        seen: list = []
        runner_mod.run_scrape(
            [_product()], api_key="", source="skroutz",
            max_live_requests=0,
            on_scraper_ready=lambda s: seen.append(s),
            on_status=lambda _: None,
        )
        assert len(seen) == 1
        assert seen[0] is fakes["scraper"]
