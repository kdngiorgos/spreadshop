from __future__ import annotations
import logging
import re
from pathlib import Path

import pdfplumber

from .base import ProductRecord, ParseError

logger = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"(\d+)[,.](\d{1,2})")


def _parse_price_str(raw: str | None) -> float | None:
    """Extract a price from a potentially garbled string like '7,02' or 's16,41'."""
    if raw is None:
        return None
    m = _PRICE_RE.search(str(raw))
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


def parse_biotonics_pdf(path: Path) -> tuple[list[ProductRecord], list[ParseError]]:
    """Parse Bio Tonics PDF pricelist (same layout as the XLSX version).

    Columns: ΚΩΔΙΚΟΣ | ΠΕΡΙΓΡΑΦΗ | ΧΤ | ΠΛΤ | BARCODE
    Category headers appear as rows with only column 0 populated.
    """
    products: list[ProductRecord] = []
    errors: list[ParseError] = []
    current_category = ""
    row_num = 0

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_num += 1
                    if not row or all(c is None or str(c).strip() == "" for c in row):
                        continue

                    cells = [str(c).strip() if c is not None else "" for c in row]

                    # Header row
                    if cells[0].upper() in ("ΚΩΔΙΚΟΣ", "CODE"):
                        continue

                    # Need at least 4 columns
                    if len(cells) < 4:
                        continue

                    code_v, name_v, wh_v, rt_v = cells[0], cells[1], cells[2], cells[3]
                    bc_v = cells[4] if len(cells) > 4 else ""

                    # Category row: code-like in col0, nothing useful in price cols
                    if name_v == "" and wh_v == "" and rt_v == "":
                        if code_v:
                            current_category = code_v
                        continue

                    # Skip if no product name
                    if not name_v:
                        continue

                    wholesale = _parse_price_str(wh_v)
                    retail = _parse_price_str(rt_v)

                    if wholesale is None or retail is None:
                        errors.append(ParseError(
                            filename=path.name,
                            row=row_num,
                            reason=f"Could not parse prices: XT={wh_v!r} PLT={rt_v!r}",
                            raw=str(cells),
                        ))
                        continue

                    if wholesale <= 0 or retail <= 0:
                        errors.append(ParseError(
                            filename=path.name,
                            row=row_num,
                            reason=f"Zero or negative price: wholesale={wholesale} retail={retail}",
                            raw=str(cells),
                        ))
                        logger.warning(
                            "Row %d in %s has zero/negative price — skipped", row_num, path.name
                        )
                        continue

                    products.append(ProductRecord(
                        source="biotonics",
                        code=code_v,
                        name=name_v,
                        wholesale_price=wholesale,
                        retail_price=retail,
                        barcode=bc_v,
                        category=current_category,
                    ))

    logger.info(
        "Bio Tonics PDF parse complete: %d products, %d errors", len(products), len(errors)
    )
    return products, errors
