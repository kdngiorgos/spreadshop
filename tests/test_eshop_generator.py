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


# ---------------------------------------------------------------------------
# T3 — Skroutz signals in product dict + honest review rendering
# ---------------------------------------------------------------------------

def _analysis_with_reviews(review_count=0, rating=0.0, shop_count=3) -> ProductAnalysis:
    p = ProductRecord(
        source="test", code="C1", name="Omega 3 1000mg",
        wholesale_price=8.0, retail_price=22.0,
        barcode="EAN999", category="Ω-Λιπαρά Οξέα",
    )
    s = SkroutzResult(
        found=True, product_name="Omega 3 1000mg",
        product_url="https://skroutz.gr/x",
        lowest_price=14.0, highest_price=18.0,
        shop_count=shop_count, rating=rating,
        review_count=review_count, match_confidence=0.9,
        search_query="Omega 3",
    )
    return ProductAnalysis(p, s)


class TestT3Signals:
    def test_product_dict_carries_skroutz_signals(self, tmp_path):
        out = generate_eshop(
            [_analysis_with_reviews(review_count=23, rating=4.2, shop_count=7)],
            tmp_path / "site", default_site_config(), template="t3",
        )
        import json
        meta = json.loads((out / "site_config.json").read_text(encoding="utf-8"))
        assert meta["template"] == "t3"
        # Verify the product dict fields reach the rendered HTML (proxy: they appear
        # in the product page since they're rendered by the template).
        product_pages = list((out / "product").glob("*.html"))
        assert len(product_pages) == 1
        html = product_pages[0].read_text(encoding="utf-8")
        assert "23" in html        # review_count
        assert "4.2" in html       # rating
        assert "7" in html         # shop_count
        assert "EAN999" in html    # barcode

    def test_t3_no_fake_reviews(self, tmp_path):
        out = generate_eshop(
            [_analysis_with_reviews(review_count=0, rating=0.0)],
            tmp_path / "site", default_site_config(), template="t3",
        )
        index_html = (out / "index.html").read_text(encoding="utf-8")
        product_html = list((out / "product").glob("*.html"))[0].read_text(encoding="utf-8")
        for html in (index_html, product_html):
            # Confirm the old fake-data patterns are completely absent
            assert "range(" not in html
            assert "| random" not in html
            # When review_count == 0, no review row should appear
            assert "κριτικές" not in html  # "κριτικές"

    def test_t3_real_review_row_present_when_review_count_positive(self, tmp_path):
        out = generate_eshop(
            [_analysis_with_reviews(review_count=42, rating=4.7)],
            tmp_path / "site", default_site_config(), template="t3",
        )
        index_html = (out / "index.html").read_text(encoding="utf-8")
        product_html = list((out / "product").glob("*.html"))[0].read_text(encoding="utf-8")
        # "κριτικές" should appear in both pages when review_count > 0
        assert "κριτικές" in index_html
        assert "κριτικές" in product_html
        assert "42" in index_html
        assert "4.7" in product_html


# ---------------------------------------------------------------------------
# T1 — Editorial redesign regressions
# ---------------------------------------------------------------------------

def _t1_analysis(name="Test Product", barcode="B001", category="Vitamins",
                 wholesale=5.0, retail=14.99, lowest=11.0,
                 shop_count=0, rating=0.0, review_count=0) -> ProductAnalysis:
    p = ProductRecord(source="test", code="X", name=name,
                      wholesale_price=wholesale, retail_price=retail,
                      barcode=barcode, category=category)
    s = SkroutzResult(
        found=(shop_count > 0), product_name=name,
        product_url="https://skroutz.gr/x",
        lowest_price=lowest, highest_price=lowest * 1.1,
        shop_count=shop_count, rating=rating, review_count=review_count,
        match_confidence=0.9, search_query=name,
    )
    return ProductAnalysis(p, s)


class TestT1Editorial:
    def test_no_gradient_hero_or_metric_pills(self, tmp_path):
        """T1 must not have the old gradient-hero or metric-pill pattern."""
        out = generate_eshop(
            [_t1_analysis() for _ in range(6)],
            tmp_path / "site", default_site_config(), template="t1",
        )
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "linear-gradient(135deg" not in html
        # The old metric pills rendered this string:
        assert "Κατηγορίες" not in html or "bg-opacity" not in html

    def test_uses_editorial_typography(self, tmp_path):
        """T1 must load Fraunces and Inter Tight from Google Fonts."""
        out = generate_eshop(
            [_t1_analysis()], tmp_path / "site", default_site_config(), template="t1",
        )
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Fraunces" in html
        assert "Inter+Tight" in html or "Inter Tight" in html

    def test_card_feature_class_on_every_fifth_card(self, tmp_path):
        """Every 5th card (index 0, 5, 10) must carry class card-feature."""
        analyses = [_t1_analysis(name=f"Product {i}", barcode=f"B{i:03d}") for i in range(12)]
        out = generate_eshop(analyses, tmp_path / "site", default_site_config(), template="t1")
        html = (out / "index.html").read_text(encoding="utf-8")
        # card-feature in a class attribute (not CSS selectors) → 3 occurrences for 12 products
        assert html.count('card-feature"') == 3

    def test_skroutz_signals_shown_when_present(self, tmp_path):
        """T1 product page shows review row and shop_count only when data present."""
        with_data = _t1_analysis(shop_count=9, rating=4.3, review_count=55)
        no_data   = _t1_analysis(name="No Signal", barcode="B999")
        out = generate_eshop([with_data, no_data], tmp_path / "site",
                              default_site_config(), template="t1")
        for html_path in (out / "product").glob("*.html"):
            html = html_path.read_text(encoding="utf-8")
            if "no-signal" in html_path.name:
                assert "καταστήματα" not in html
                assert "κριτικές" not in html
            else:
                assert "9" in html
                assert "κριτικές" in html
                assert "55" in html


# ---------------------------------------------------------------------------
# T2 — JS hooks regression (class name fix)
# ---------------------------------------------------------------------------

class TestT2JSHooks:
    def test_uses_canonical_class_names(self, tmp_path):
        """T2 must use .product-card and .filter-pill (not the old -elevate/-tab variants)."""
        out = generate_eshop(
            [_t1_analysis()], tmp_path / "site", default_site_config(), template="t2",
        )
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "product-card-elevate" not in html
        assert "filter-pill-tab" not in html
        assert 'class="product-card"' in html
        assert "filter-pill" in html
