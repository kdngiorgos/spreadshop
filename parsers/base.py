from __future__ import annotations
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProductRecord:
    source: str              # supplier slug, e.g. "biotonics", "viogenesis"
    code: str                # supplier product code
    name: str                # product name / description
    wholesale_price: float   # ΧΤ — what the reseller pays
    retail_price: float      # ΠΛΤ / ΛΤ — suggested retail
    barcode: str             # EAN barcode
    category: str = ""       # category from source file


@dataclass
class SkroutzResult:
    found: bool
    product_name: str = ""
    product_url: str = ""
    lowest_price: float = 0.0
    highest_price: float = 0.0
    shop_count: int = 0
    rating: float = 0.0
    review_count: int = 0
    match_confidence: float = 0.0
    search_query: str = ""
    skroutz_id: Optional[int] = None


@dataclass
class ParseError:
    filename: str
    row: int
    reason: str
    raw: Optional[str] = None


# ---------------------------------------------------------------------------
# Supplier registry
# Maps lowercase keyword (appears in filename) → parser function importer.
# To add a new supplier: add one entry here — no other code changes needed.
# ---------------------------------------------------------------------------
def _build_registry() -> dict[str, callable]:
    """Build supplier registry lazily to avoid import-time circular deps."""
    from .pdf_viogenesis import parse_viogenesis_pdf
    from .pdf_biotonics import parse_biotonics_pdf
    return {
        "viogenesis": parse_viogenesis_pdf,
        "biotonics":  parse_biotonics_pdf,
        "atcare":     parse_biotonics_pdf,   # Atcare uses the Bio Tonics PDF format
    }


def parse_file(
    filepath: str | Path,
) -> tuple[list[ProductRecord], list[ParseError], list[str]]:
    """Dispatch to the correct parser based on file type and content.

    Returns:
        (products, errors, warnings) — warnings is a list of human-readable
        strings to surface in the UI (e.g. unknown supplier fallback notice).
    """
    path = Path(filepath)
    suffix = path.suffix.lower()
    ui_warnings: list[str] = []

    if suffix == ".xlsx":
        from .xlsx_parser import parse_xlsx
        logger.info("Parsing XLSX: %s", path.name)
        products, errors = parse_xlsx(path)
        logger.info("XLSX parse complete: %d products, %d errors", len(products), len(errors))
        return products, errors, ui_warnings

    if suffix == ".pdf":
        name_lower = path.name.lower()
        registry = _build_registry()

        for keyword, parser in registry.items():
            if keyword in name_lower:
                logger.info("Parsing PDF (%s): %s", keyword, path.name)
                products, errors = parser(path)
                logger.info("PDF parse complete: %d products, %d errors", len(products), len(errors))
                return products, errors, ui_warnings

        # No recognised keyword — fall back to Bio Tonics parser with a warning
        msg = (
            f"Unknown supplier for '{path.name}' — defaulting to Bio Tonics parser. "
            "Rename the file to include the supplier name (e.g. 'viogenesis', 'biotonics') "
            "for automatic detection."
        )
        ui_warnings.append(msg)
        logger.warning(msg)
        from .pdf_biotonics import parse_biotonics_pdf
        products, errors = parse_biotonics_pdf(path)
        return products, errors, ui_warnings

    raise ValueError(f"Unsupported file type: {suffix}")
