"""Unit tests for scraper.cache.ScrapeCache."""
from __future__ import annotations

import json
import time

import pytest

from parsers.base import SkroutzResult
from scraper.cache import ScrapeCache
from config import CACHE_SCHEMA_VERSION


def _result(found=True, name="X", price=10.0) -> SkroutzResult:
    return SkroutzResult(
        found=found,
        product_name=name,
        product_url="https://example.gr/x",
        lowest_price=price,
        highest_price=price,
        shop_count=3,
        rating=4.5,
        review_count=12,
        match_confidence=0.9,
        search_query=name,
        skroutz_id=42,
        image_url="https://cdn.example.gr/img.jpg",
    )


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestKey:
    def test_barcode_wins_when_present(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        assert c._key("5012345678900", "Some Name") == "5012345678900"

    def test_name_fallback_lowercased(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        assert c._key("", "Vitamin C 1000mg") == "vitamin c 1000mg"

    def test_name_fallback_truncated_to_60_chars(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        long_name = "A" * 100
        assert c._key("", long_name) == ("a" * 60)


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_put_then_get_returns_equivalent_object(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        original = _result(price=19.99)
        c.put("123", "Foo", original)

        loaded = c.get("123", "Foo")
        assert loaded is not None
        assert loaded.found is True
        assert loaded.product_name == "X"
        assert loaded.lowest_price == 19.99
        assert loaded.skroutz_id == 42
        assert loaded.image_url == "https://cdn.example.gr/img.jpg"

    def test_has_returns_true_after_put(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        c.put("123", "Foo", _result())
        assert c.has("123", "Foo") is True

    def test_has_returns_false_for_missing_key(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        assert c.has("nope", "nope") is False

    def test_get_returns_none_for_missing_key(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        assert c.get("nope", "nope") is None


# ---------------------------------------------------------------------------
# Persistence (file written on put)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_put_writes_to_disk(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        c.put("123", "Foo", _result())
        assert (tmp_path / "skroutz_cache.json").exists()

    def test_second_instance_reads_existing_file(self, tmp_path):
        c1 = ScrapeCache(cache_dir=tmp_path)
        c1.put("123", "Foo", _result(price=7.5))

        c2 = ScrapeCache(cache_dir=tmp_path)
        loaded = c2.get("123", "Foo")
        assert loaded is not None
        assert loaded.lowest_price == 7.5

    def test_corrupt_file_resets_to_empty(self, tmp_path):
        (tmp_path / "skroutz_cache.json").write_text("{not valid json")
        c = ScrapeCache(cache_dir=tmp_path)  # must not raise
        assert c.size == 0


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

class TestTTL:
    def test_expired_entry_returns_none(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path, ttl=1)
        c.put("123", "Foo", _result())
        time.sleep(1.1)
        assert c.get("123", "Foo") is None

    def test_fresh_entry_within_ttl_returns_value(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path, ttl=60)
        c.put("123", "Foo", _result())
        assert c.get("123", "Foo") is not None


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_old_schema_entry_is_dropped(self, tmp_path):
        # Hand-craft a cache file with a stale schema version
        path = tmp_path / "skroutz_cache.json"
        path.write_text(json.dumps({
            "123": {
                "v": CACHE_SCHEMA_VERSION - 1,
                "ts": time.time(),
                "result": {"found": True, "lowest_price": 5.0},
            }
        }), encoding="utf-8")

        c = ScrapeCache(cache_dir=tmp_path)
        assert c.get("123", "Foo") is None

    def test_missing_v_field_treated_as_old_schema(self, tmp_path):
        path = tmp_path / "skroutz_cache.json"
        path.write_text(json.dumps({
            "123": {"ts": time.time(), "result": {"found": True}}
        }), encoding="utf-8")
        c = ScrapeCache(cache_dir=tmp_path)
        assert c.get("123", "Foo") is None


# ---------------------------------------------------------------------------
# clear() and size
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_in_memory_and_disk(self, tmp_path):
        c = ScrapeCache(cache_dir=tmp_path)
        c.put("a", "A", _result())
        c.put("b", "B", _result())
        assert c.size == 2

        c.clear()
        assert c.size == 0

        c2 = ScrapeCache(cache_dir=tmp_path)
        assert c2.size == 0


# ---------------------------------------------------------------------------
# Forward compat — extra fields in cached dict don't break load
# ---------------------------------------------------------------------------

class TestForwardCompat:
    def test_extra_unknown_fields_ignored(self, tmp_path):
        path = tmp_path / "skroutz_cache.json"
        path.write_text(json.dumps({
            "123": {
                "v": CACHE_SCHEMA_VERSION,
                "ts": time.time(),
                "result": {
                    "found": True,
                    "lowest_price": 8.0,
                    "future_field_we_dont_know": "ignore me",
                },
            }
        }), encoding="utf-8")

        c = ScrapeCache(cache_dir=tmp_path)
        loaded = c.get("123", "Foo")
        assert loaded is not None
        assert loaded.lowest_price == 8.0
