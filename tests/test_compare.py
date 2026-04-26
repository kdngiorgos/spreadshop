"""Unit tests for analysis.compare — ProductAnalysis and analyze()."""
from __future__ import annotations

from analysis.compare import ProductAnalysis, analyze
from parsers.base import ProductRecord, SkroutzResult


def _product(wholesale=10.0, retail=20.0, name="Foo", barcode="123", category="cat") -> ProductRecord:
    return ProductRecord(
        source="test",
        code="C1",
        name=name,
        wholesale_price=wholesale,
        retail_price=retail,
        barcode=barcode,
        category=category,
    )


def _skroutz(found=True, lowest=15.0, shops=5, reviews=12) -> SkroutzResult:
    return SkroutzResult(
        found=found,
        product_name="Foo on Skroutz",
        product_url="https://skroutz.gr/x",
        lowest_price=lowest,
        highest_price=lowest,
        shop_count=shops,
        rating=4.0,
        review_count=reviews,
        match_confidence=0.9,
        search_query="Foo",
        skroutz_id=99,
    )


# ---------------------------------------------------------------------------
# Margin / undercut math
# ---------------------------------------------------------------------------

class TestMargin:
    def test_margin_absolute_and_percent(self):
        a = ProductAnalysis(_product(wholesale=10.0, retail=20.0), _skroutz(lowest=15.0))
        assert a.margin_absolute == 5.0
        assert a.margin_pct == 50.0

    def test_undercut_vs_retail(self):
        a = ProductAnalysis(_product(wholesale=10.0, retail=20.0), _skroutz(lowest=15.0))
        # (20 - 15) / 20 * 100 = 25.0
        assert a.undercut_vs_retail == 25.0

    def test_zero_wholesale_does_not_crash(self):
        a = ProductAnalysis(_product(wholesale=0.0, retail=20.0), _skroutz(lowest=10.0))
        assert a.margin_pct == 0.0

    def test_zero_retail_does_not_crash(self):
        a = ProductAnalysis(_product(wholesale=10.0, retail=0.0), _skroutz(lowest=15.0))
        assert a.undercut_vs_retail == 0.0


# ---------------------------------------------------------------------------
# Recommendation thresholds
# ---------------------------------------------------------------------------

class TestRecommendation:
    def test_strong_buy_high_margin_low_competition(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=15.0, shops=5))
        # margin = 50% (≥30), shops = 5 (≤10) → strong_buy
        assert a.recommendation == "strong_buy"

    def test_consider_when_shops_over_strong_buy_threshold(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=15.0, shops=12))
        # margin = 50%, shops = 12 (>10 strong_buy max) → consider (margin still ≥15)
        assert a.recommendation == "consider"

    def test_consider_when_margin_between_15_and_30(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=12.0, shops=5))
        # margin = 20% → consider
        assert a.recommendation == "consider"

    def test_skip_when_margin_below_consider_threshold(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=11.0, shops=5))
        # margin = 10% (<15) → skip
        assert a.recommendation == "skip"

    def test_skip_when_margin_negative(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=8.0, shops=5))
        # margin = -20% → skip
        assert a.recommendation == "skip"

    def test_not_found_when_skroutz_found_false(self):
        a = ProductAnalysis(_product(), _skroutz(found=False))
        assert a.recommendation == "not_found"

    def test_not_found_when_lowest_price_zero(self):
        a = ProductAnalysis(_product(), _skroutz(found=True, lowest=0.0))
        assert a.recommendation == "not_found"


# ---------------------------------------------------------------------------
# Competition level mapping
# ---------------------------------------------------------------------------

class TestCompetitionLevel:
    def test_low_when_shops_at_threshold(self):
        a = ProductAnalysis(_product(), _skroutz(shops=4))
        assert a.competition_level == "Low"

    def test_medium_at_upper_bound(self):
        a = ProductAnalysis(_product(), _skroutz(shops=15))
        assert a.competition_level == "Medium"

    def test_high_above_medium_max(self):
        a = ProductAnalysis(_product(), _skroutz(shops=20))
        assert a.competition_level == "High"

    def test_default_dash_when_not_found(self):
        a = ProductAnalysis(_product(), _skroutz(found=False))
        assert a.competition_level == "—"


# ---------------------------------------------------------------------------
# Opportunity score
# ---------------------------------------------------------------------------

class TestOpportunityScore:
    def test_score_is_zero_when_not_found(self):
        a = ProductAnalysis(_product(), _skroutz(found=False))
        assert a.opportunity_score == 0.0

    def test_score_in_zero_to_hundred_range(self):
        a = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=200.0, shops=0, reviews=500))
        assert 0.0 <= a.opportunity_score <= 100.0

    def test_higher_margin_gives_higher_score(self):
        low_margin = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=12.0, shops=5, reviews=10))
        high_margin = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=20.0, shops=5, reviews=10))
        assert high_margin.opportunity_score > low_margin.opportunity_score

    def test_more_competition_lowers_score(self):
        low_comp = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=15.0, shops=2, reviews=10))
        high_comp = ProductAnalysis(_product(wholesale=10.0), _skroutz(lowest=15.0, shops=25, reviews=10))
        assert low_comp.opportunity_score > high_comp.opportunity_score


# ---------------------------------------------------------------------------
# analyze() — list construction, sorting, key resolution
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_empty_inputs_return_empty(self):
        assert analyze([], {}) == []

    def test_results_keyed_by_barcode(self):
        p = _product(barcode="EAN-1")
        r = _skroutz(lowest=15.0)
        out = analyze([p], {"EAN-1": r})
        assert len(out) == 1
        assert out[0].skroutz.lowest_price == 15.0

    def test_results_keyed_by_name_when_no_barcode(self):
        p = _product(barcode="", name="Vitamin C 1000mg")
        r = _skroutz(lowest=15.0)
        # Same key the cache uses: name[:60].lower()
        out = analyze([p], {"vitamin c 1000mg": r})
        assert out[0].skroutz.lowest_price == 15.0

    def test_missing_result_yields_not_found_analysis(self):
        out = analyze([_product(barcode="EAN-1")], {})
        assert len(out) == 1
        assert out[0].recommendation == "not_found"

    def test_sorted_by_score_descending(self):
        p_high = _product(barcode="HI", wholesale=10.0)
        p_low  = _product(barcode="LO", wholesale=10.0)
        results = {
            "HI": _skroutz(lowest=20.0, shops=2, reviews=50),    # high score
            "LO": _skroutz(lowest=11.0, shops=20, reviews=1),    # low score
        }
        out = analyze([p_low, p_high], results)
        assert out[0].product.barcode == "HI"
        assert out[1].product.barcode == "LO"
