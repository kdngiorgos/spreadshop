"""Tests for Bio Tonics PDF parser."""
import pytest
from parsers.pdf_biotonics import _parse_price_str, parse_biotonics_pdf
from config import PRICE_RATIO_MIN, PRICE_RATIO_MAX

_KNOWN_CATEGORY_HEADERS = {
    "ΒΙΤΑΜΙΝΕΣ", "ΜΕΤΑΛΛΑ", "ΙΧΝΟΣΤΟΙΧΕΙΑ", "ΠΡΩΤΕΪΝΕΣ",
    "ΑΜΙΝΟΞΕΑ", "ΛΙΠΑΡΑ ΟΞΕΑ", "ΠΡΟΒΙΟΤΙΚΑ", "ΕΝΖΥΜΑ",
}


# ---------------------------------------------------------------------------
# Unit tests for _parse_price_str
# ---------------------------------------------------------------------------

class TestParsePriceStr:
    def test_comma_decimal(self):
        assert _parse_price_str("7,02") == pytest.approx(7.02)

    def test_dot_decimal(self):
        assert _parse_price_str("7.02") == pytest.approx(7.02)

    def test_garbled_prefix(self):
        # Typical garbled cell: leading characters before the number
        assert _parse_price_str("s16,41") == pytest.approx(16.41)

    def test_none_returns_none(self):
        assert _parse_price_str(None) is None

    def test_no_match_returns_none(self):
        assert _parse_price_str("n/a") is None

    def test_empty_string_returns_none(self):
        assert _parse_price_str("") is None


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestBioTonicsPdfIntegration:
    def test_product_count(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        # PDF extraction may miss 1-2 rows vs XLSX; allow a small tolerance
        assert len(products) >= 120

    def test_source_slug(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        assert all(p.source == "biotonics" for p in products)

    def test_all_prices_positive(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        assert all(p.wholesale_price > 0 for p in products)
        assert all(p.retail_price > 0 for p in products)

    def test_price_ratio_range(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        bad = [
            p for p in products
            if not (PRICE_RATIO_MIN <= p.wholesale_price / p.retail_price <= PRICE_RATIO_MAX)
        ]
        assert bad == [], f"Products outside ratio range: {[(p.name, p.wholesale_price, p.retail_price) for p in bad]}"

    def test_no_category_header_as_product(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        bad = [p for p in products if p.name.upper() in _KNOWN_CATEGORY_HEADERS]
        assert bad == [], f"Category header rows parsed as products: {[p.name for p in bad]}"

    def test_multiple_categories_present(self, biotonics_pdf_path):
        products, _ = parse_biotonics_pdf(biotonics_pdf_path)
        categories = {p.category for p in products if p.category}
        assert len(categories) >= 3, f"Expected multiple categories, got: {categories}"
