"""Tests for Bio Tonics XLSX parser."""
import pytest
from parsers.xlsx_parser import _parse_price, parse_xlsx
from config import PRICE_RATIO_MIN, PRICE_RATIO_MAX

# Known category header strings from the Bio Tonics file
_KNOWN_CATEGORY_HEADERS = {
    "ΒΙΤΑΜΙΝΕΣ", "ΜΕΤΑΛΛΑ", "ΙΧΝΟΣΤΟΙΧΕΙΑ", "ΠΡΩΤΕΪΝΕΣ",
    "ΑΜΙΝΟΞΕΑ", "ΛΙΠΑΡΑ ΟΞΕΑ", "ΠΡΟΒΙΟΤΙΚΑ", "ΕΝΖΥΜΑ",
}


# ---------------------------------------------------------------------------
# Unit tests for _parse_price
# ---------------------------------------------------------------------------

class TestParsePrice:
    def test_numeric_float(self):
        assert _parse_price(7.02) == pytest.approx(7.02)

    def test_numeric_int(self):
        assert _parse_price(10) == pytest.approx(10.0)

    def test_string_comma_decimal(self):
        assert _parse_price("7,02") == pytest.approx(7.02)

    def test_string_dot_decimal(self):
        assert _parse_price("11.77") == pytest.approx(11.77)

    def test_string_with_euro(self):
        assert _parse_price("€ 11,77") == pytest.approx(11.77)

    def test_none_returns_none(self):
        assert _parse_price(None) is None

    def test_non_numeric_string_returns_none(self):
        assert _parse_price("N/A") is None

    def test_empty_string_returns_none(self):
        assert _parse_price("") is None


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestXlsxParserIntegration:
    def test_product_count(self, xlsx_path):
        products, errors = parse_xlsx(xlsx_path)
        assert len(products) == 125
        assert len(errors) == 0

    def test_source_slug(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        assert all(p.source == "biotonics" for p in products)

    def test_all_prices_positive(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        assert all(p.wholesale_price > 0 for p in products)
        assert all(p.retail_price > 0 for p in products)

    def test_price_ratio_range(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        bad = [
            p for p in products
            if not (PRICE_RATIO_MIN <= p.wholesale_price / p.retail_price <= PRICE_RATIO_MAX)
        ]
        assert bad == [], f"Products outside ratio range: {[(p.name, p.wholesale_price, p.retail_price) for p in bad]}"

    def test_no_category_header_as_product(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        bad = [p for p in products if p.name.upper() in _KNOWN_CATEGORY_HEADERS]
        assert bad == [], f"Category header rows parsed as products: {[p.name for p in bad]}"

    def test_barcodes_no_float_suffix(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        bad = [p for p in products if p.barcode.endswith(".0")]
        assert bad == [], f"Barcodes with float suffix: {[p.barcode for p in bad]}"

    def test_at_least_one_category_set(self, xlsx_path):
        products, _ = parse_xlsx(xlsx_path)
        with_category = [p for p in products if p.category]
        assert len(with_category) > 0, "No products have a category set"
