"""Tests for VioGenesis garble decoder and PDF parser."""
import pytest
from parsers.pdf_viogenesis import _extract_xt, _extract_rt, _valid_ratio, parse_viogenesis_pdf


# ---------------------------------------------------------------------------
# _extract_xt — wholesale price decoding
# ---------------------------------------------------------------------------

class TestExtractXt:
    @pytest.mark.parametrize("raw,expected", [
        # Main pattern: gsr{d1}//{d2}...\w,{cents}
        ("iasd.gsr2//22w,400p1 €", 22.40),
        ("iasd.gsr1//92w,108p2 €", 19.10),
        ("iasd.gsr3//52w,205p2 €", 35.20),
    ])
    def test_main_pattern(self, raw, expected):
        assert _extract_xt(raw) == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize("raw,expected", [
        # Single-digit pattern: gsr/{d1}/digits,\w?{cents}
        ("iasd.gsr/9/2,w608p2 €", 9.60),
    ])
    def test_single_digit_pattern(self, raw, expected):
        assert _extract_xt(raw) == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize("raw,expected", [
        # Ads pattern: ads{d1?}/{d2}digits,{cents}
        ("ads3/52,0071", 35.00),
        ("ads/72,4072",   7.40),
    ])
    def test_ads_pattern(self, raw, expected):
        assert _extract_xt(raw) == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize("raw,expected", [
        # Last-resort: clean numeric string
        ("22,40",  22.40),
        ("22.40",  22.40),
        ("9,60",    9.60),
    ])
    def test_last_resort_plain_numeric(self, raw, expected):
        assert _extract_xt(raw) == pytest.approx(expected, abs=0.01)

    def test_none_input_returns_none(self):
        assert _extract_xt(None) is None

    def test_empty_string_returns_none(self):
        assert _extract_xt("") is None

    def test_no_digits_returns_none(self):
        assert _extract_xt("n/a") is None

    def test_out_of_range_returns_none(self):
        # Value 0.50 is below the 1.0 floor
        assert _extract_xt("0,50") is None


# ---------------------------------------------------------------------------
# _extract_rt — retail price decoding
# ---------------------------------------------------------------------------

class TestExtractRt:
    @pytest.mark.parametrize("raw,expected", [
        ("/eVnito/3Gu7p,e5nl0o e€", 37.50),
        ("/eVnito/2Gu8p,e5nl0o e€", 28.50),
        ("/Vio5G8,e7n0 e€",         58.70),
        ("/Vio2G2,e0n0 e€",         22.00),
    ])
    def test_digit_extraction(self, raw, expected):
        assert _extract_rt(raw) == pytest.approx(expected, abs=0.01)

    def test_none_input_returns_none(self):
        assert _extract_rt(None) is None

    def test_insufficient_digits_returns_none(self):
        # Only 3 individual digits — not enough to form a price
        assert _extract_rt("a1b2c3") is None

    def test_empty_string_returns_none(self):
        assert _extract_rt("") is None


# ---------------------------------------------------------------------------
# _valid_ratio
# ---------------------------------------------------------------------------

class TestValidRatio:
    def test_typical_ratio_is_valid(self):
        # 22.40 / 37.50 ≈ 0.597 — squarely in range
        assert _valid_ratio(22.40, 37.50) is True

    def test_low_ratio_is_invalid(self):
        assert _valid_ratio(1.0, 37.50) is False

    def test_high_ratio_is_invalid(self):
        # ratio > 0.78
        assert _valid_ratio(35.0, 37.50) is False

    def test_zero_retail_is_invalid(self):
        assert _valid_ratio(22.40, 0.0) is False

    def test_boundary_min(self):
        # exactly 0.48 → valid
        assert _valid_ratio(4.80, 10.0) is True

    def test_boundary_max(self):
        # exactly 0.78 → valid
        assert _valid_ratio(7.80, 10.0) is True


# ---------------------------------------------------------------------------
# Integration — full PDF parse
# ---------------------------------------------------------------------------

class TestVioGenesisPdfIntegration:
    def test_product_count(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        assert len(products) == 82

    def test_source_slug(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        assert all(p.source == "viogenesis" for p in products)

    def test_all_prices_in_ratio_range(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        bad = [
            p for p in products
            if not _valid_ratio(p.wholesale_price, p.retail_price)
        ]
        assert bad == [], f"Products outside ratio range: {bad}"

    def test_no_ratio_warning_in_errors(self, viogenesis_pdf_path):
        _, errors = parse_viogenesis_pdf(viogenesis_pdf_path)
        ratio_warnings = [e for e in errors if "High ratio-failure rate" in e.reason]
        assert ratio_warnings == [], "Ratio-failure warning triggered — patterns may be degrading"

    def test_barcodes_numeric_only(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        bad = [p for p in products if p.barcode and not p.barcode.isdigit()]
        assert bad == [], f"Non-numeric barcodes found: {[p.barcode for p in bad]}"

    def test_no_pipe_in_category(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        bad = [p for p in products if "|" in p.category]
        assert bad == [], f"Pipe not stripped from category: {[p.category for p in bad]}"

    def test_all_prices_positive(self, viogenesis_pdf_path):
        products, _ = parse_viogenesis_pdf(viogenesis_pdf_path)
        assert all(p.wholesale_price > 0 for p in products)
        assert all(p.retail_price > 0 for p in products)
