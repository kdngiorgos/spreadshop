"""Unit tests for eshop.generator — slug helpers and end-to-end render."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("jinja2", reason="jinja2 not installed — skipping eshop tests")

from analysis.compare import ProductAnalysis
from eshop.generator import _slugify, _unique_slugs, generate_eshop
from eshop.site_config import default_site_config
from parsers.base import ProductRecord, SkroutzResult


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic_ascii(self):
        assert _slugify("Vitamin C 1000mg") == "vitamin-c-1000mg"

    def test_collapses_whitespace_and_hyphens(self):
        assert _slugify("Foo  --  Bar") == "foo-bar"

    def test_strips_punctuation(self):
        assert _slugify("B-Complex (60 caps)!") == "b-complex-60-caps"

    def test_truncates_to_60_chars(self):
        s = _slugify("a" * 200)
        assert len(s) <= 60

    def test_greek_only_falls_back_to_barcode(self):
        # Pure Greek strips entirely → falls back to barcode (alphanumeric only — hyphens dropped)
        assert _slugify("Βιταμίνη", fallback="EAN-12345") == "EAN12345"

    def test_fallback_when_input_empty(self):
        assert _slugify("", fallback="ABC123") == "ABC123"

    def test_default_fallback_is_product(self):
        # No usable text and no fallback → "product"
        assert _slugify("") == "product"


# ---------------------------------------------------------------------------
# _unique_slugs
# ---------------------------------------------------------------------------

class TestUniqueSlugs:
    def test_no_duplicates_passthrough(self):
        items = [{"slug": "a"}, {"slug": "b"}]
        out = _unique_slugs(items)
        assert [p["slug"] for p in out] == ["a", "b"]

    def test_duplicates_get_numeric_suffix(self):
        items = [{"slug": "x"}, {"slug": "x"}, {"slug": "y"}]
        out = _unique_slugs(items)
        assert out[0]["slug"] == "x-1"
        assert out[1]["slug"] == "x-2"
        assert out[2]["slug"] == "y"


# ---------------------------------------------------------------------------
# generate_eshop — end-to-end into tmp_path
# ---------------------------------------------------------------------------

def _analysis(name="Foo", barcode="EAN1", image_url="", category="Vitamins") -> ProductAnalysis:
    p = ProductRecord(
        source="test", code="C1", name=name,
        wholesale_price=10.0, retail_price=20.0,
        barcode=barcode, category=category,
    )
    s = SkroutzResult(
        found=True, product_name=name, product_url="https://skroutz.gr/x",
        lowest_price=15.0, highest_price=15.0, shop_count=3,
        rating=4.5, review_count=20, match_confidence=0.9,
        search_query=name, image_url=image_url,
    )
    return ProductAnalysis(p, s)


class TestGenerateEshop:
    def test_renders_index_and_product_pages(self, tmp_path):
        analyses = [
            _analysis(name="Vitamin C", barcode="EAN1"),
            _analysis(name="Vitamin D", barcode="EAN2"),
        ]
        out = generate_eshop(analyses, tmp_path / "site", default_site_config())

        assert out.exists()
        assert (out / "index.html").exists()
        # Two product pages, one per analysis
        product_pages = list((out / "product").glob("*.html"))
        assert len(product_pages) == 2

    def test_static_assets_copied(self, tmp_path):
        out = generate_eshop([_analysis()], tmp_path / "site", default_site_config())
        assert (out / "static").is_dir()
        # Placeholder for missing images is included
        assert (out / "static" / "placeholder.svg").exists()

    def test_site_config_json_written(self, tmp_path):
        out = generate_eshop([_analysis()], tmp_path / "site", default_site_config())
        meta = json.loads((out / "site_config.json").read_text(encoding="utf-8"))
        assert meta["product_count"] == 1
        assert meta["template"] == "t1"

    def test_image_url_empty_uses_placeholder_branch(self, tmp_path):
        # When a product has no image, the rendered HTML should reference placeholder.svg
        out = generate_eshop(
            [_analysis(image_url="")], tmp_path / "site", default_site_config(),
        )
        index = (out / "index.html").read_text(encoding="utf-8")
        assert "placeholder.svg" in index

    def test_image_url_present_renders_img_src(self, tmp_path):
        url = "https://cdn.example.gr/product.jpg"
        out = generate_eshop(
            [_analysis(image_url=url)], tmp_path / "site", default_site_config(),
        )
        index = (out / "index.html").read_text(encoding="utf-8")
        assert url in index

    def test_unknown_template_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown template"):
            generate_eshop(
                [_analysis()], tmp_path / "site", default_site_config(),
                template="nope",
            )

    def test_existing_output_dir_is_cleared(self, tmp_path):
        out_dir = tmp_path / "site"
        out_dir.mkdir()
        (out_dir / "stale_file.txt").write_text("old")
        # Re-render
        generate_eshop([_analysis()], out_dir, default_site_config())
        assert not (out_dir / "stale_file.txt").exists()

    def test_template_t2_and_t3_render(self, tmp_path):
        for tmpl in ("t2", "t3"):
            out = generate_eshop(
                [_analysis()], tmp_path / tmpl, default_site_config(), template=tmpl,
            )
            assert (out / "index.html").exists()
