from __future__ import annotations
from dataclasses import dataclass

from parsers.base import ProductRecord, SkroutzResult
from config import (
    MARGIN_STRONG_BUY_PCT,
    MARGIN_CONSIDER_PCT,
    SHOPS_STRONG_BUY_MAX,
    SHOPS_LOW_MAX,
    SHOPS_MEDIUM_MAX,
    SCORE_MARGIN_WEIGHT,
    SCORE_COMPETITION_WEIGHT,
    SCORE_DEMAND_WEIGHT,
    SCORE_COMPETITION_BASE,
    SCORE_DEMAND_BASE,
)


@dataclass
class ProductAnalysis:
    product: ProductRecord
    skroutz: SkroutzResult

    # Computed metrics
    margin_absolute: float = 0.0       # skroutz_lowest - wholesale
    margin_pct: float = 0.0            # (margin / wholesale) * 100
    undercut_vs_retail: float = 0.0    # % the Skroutz low price is below supplier RRP
    competition_level: str = "—"       # Low / Medium / High
    opportunity_score: float = 0.0     # 0–100 composite
    recommendation: str = "not_found"  # strong_buy / consider / skip / not_found

    def __post_init__(self) -> None:
        if not self.skroutz.found or self.skroutz.lowest_price <= 0:
            self.recommendation = "not_found"
            return

        wh = self.product.wholesale_price
        rt = self.product.retail_price
        sk_low = self.skroutz.lowest_price

        self.margin_absolute = round(sk_low - wh, 2)
        self.margin_pct = round((self.margin_absolute / wh) * 100, 1) if wh else 0.0
        self.undercut_vs_retail = round(((rt - sk_low) / rt) * 100, 1) if rt else 0.0

        shops = self.skroutz.shop_count
        if shops <= SHOPS_LOW_MAX:
            self.competition_level = "Low"
        elif shops <= SHOPS_MEDIUM_MAX:
            self.competition_level = "Medium"
        else:
            self.competition_level = "High"

        # Opportunity score (0–100)
        margin_score = min(self.margin_pct / 100, 1.0) * SCORE_MARGIN_WEIGHT
        comp_score = max(0.0, (SCORE_COMPETITION_BASE - shops) / SCORE_COMPETITION_BASE) * SCORE_COMPETITION_WEIGHT
        demand_score = min(self.skroutz.review_count / SCORE_DEMAND_BASE, 1.0) * SCORE_DEMAND_WEIGHT
        self.opportunity_score = round(
            min(margin_score + comp_score + demand_score, 100.0), 1
        )

        # Recommendation
        if self.margin_pct < 0:
            self.recommendation = "skip"
        elif self.margin_pct >= MARGIN_STRONG_BUY_PCT and shops <= SHOPS_STRONG_BUY_MAX:
            self.recommendation = "strong_buy"
        elif self.margin_pct >= MARGIN_CONSIDER_PCT:
            self.recommendation = "consider"
        else:
            self.recommendation = "skip"


def analyze(
    products: list[ProductRecord],
    results: dict[str, SkroutzResult],
) -> list[ProductAnalysis]:
    """Build ProductAnalysis list from parsed products + scraped results.

    Args:
        products: All parsed product records.
        results: Mapping of barcode (or name key) → SkroutzResult.
    """
    analyses: list[ProductAnalysis] = []
    for p in products:
        key = p.barcode if p.barcode else p.name[:60].lower()
        skroutz = results.get(key, SkroutzResult(found=False, search_query=p.name))
        analyses.append(ProductAnalysis(product=p, skroutz=skroutz))
    return sorted(analyses, key=lambda a: a.opportunity_score, reverse=True)
