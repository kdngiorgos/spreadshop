from __future__ import annotations
import logging
import re
from pathlib import Path

import pdfplumber

from .base import ProductRecord, ParseError
from config import PRICE_RATIO_MIN, PRICE_RATIO_MAX, PRICE_RATIO_WARN_THRESHOLD

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VioGenesis PDF — garbled price extraction
#
# The PDF was exported with overlapping text columns, causing adjacent cell
# content to be interleaved character-by-character.
#
# XT (wholesale) column garble patterns:
#   Main:   'iasd.gsr2//22w,400p1 €'  →  integer: 2+2=22, cents: 40  →  22.40
#           'iasd.gsr1//92w,108p2 €'  →  integer: 1+9=19, cents: 10  →  19.10
#           'iasd.gsr3//52w,205p2 €'  →  integer: 3+5=35, cents: 20  →  35.20
#   Ads:    'ads3/52,0071'            →  integer: 3+5=35, cents: 00  →  35.00
#           'ads/72,4072'             →  integer: 0+7=7,  cents: 40  →   7.40
#
# LT (retail) column garble patterns:
#   Main:  '/eVnito/3Gu7p,e5nl0o e€'  →  digits 3,7,5,0  →  37.50
#          '/eVnito/2Gu8p,e5nl0o e€'  →  digits 2,8,5,0  →  28.50
#   Short: '/Vio5G8,e7n0 e€'          →  digits 5,8,7,0  →  58.70
#          '/Vio2G2,e0n0 e€'          →  digits 2,2,0,0  →  22.00
# ---------------------------------------------------------------------------

# XT patterns — tried in order
_XT_MAIN   = re.compile(r"gsr(\d)//(\d)\d*\w,(\d{2})")  # gsr1//92w,108  →  19.10
_XT_SINGLE = re.compile(r"gsr/(\d)/\d+,\w?(\d{2})")      # gsr/9/2,w60    →   9.60
_XT_ADS    = re.compile(r"ads(\d?)/(\d)\d*,(\d{2})")     # ads3/52,0071   →  35.00

# RT: extract all single/small digit groups; take first 4 → dd.dd
_RT_DIGITS = re.compile(r"\d+")


def _extract_xt(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip()

    m = _XT_MAIN.search(s)
    if m:
        val = float(f"{m.group(1)}{m.group(2)}.{m.group(3)}")
        if 1.0 <= val <= 500.0:
            return val

    m = _XT_SINGLE.search(s)
    if m:
        val = float(f"{m.group(1)}.{m.group(2)}")
        if 1.0 <= val <= 500.0:
            return val

    m = _XT_ADS.search(s)
    if m:
        prefix = m.group(1) or "0"
        val = float(f"{prefix}{m.group(2)}.{m.group(3)}")
        if 1.0 <= val <= 500.0:
            return val

    # Last resort: clean numeric string like '22,40' or '22.40'
    m = re.search(r"(\d{1,3})[,.](\d{2})", s)
    if m:
        val = float(f"{m.group(1)}.{m.group(2)}")
        if 1.0 <= val <= 500.0:
            return val

    return None


def _extract_rt(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip()

    # Extract all digit groups; combine first 4 individual digits into DD.DD
    all_digits = re.findall(r"\d+", s)
    individual = []
    for group in all_digits:
        for ch in group:
            individual.append(ch)
            if len(individual) == 4:
                break
        if len(individual) == 4:
            break

    if len(individual) == 4:
        val = float(f"{individual[0]}{individual[1]}.{individual[2]}{individual[3]}")
        if 1.0 <= val <= 500.0:
            return val

    return None


def _valid_ratio(wh: float, rt: float) -> bool:
    if rt == 0:
        return False
    return PRICE_RATIO_MIN <= wh / rt <= PRICE_RATIO_MAX


def parse_viogenesis_pdf(path: Path) -> tuple[list[ProductRecord], list[ParseError]]:
    """Parse VioGenesis PDF product list.

    Column mapping (0-indexed):
      0: BARCODE   1: code   2: product name (clean, not garbled)
      6: categories   9: ΧΤ (wholesale, garbled)   10: ΛΤ (retail, garbled)
    """
    products: list[ProductRecord] = []
    errors: list[ParseError] = []
    row_num = 0
    ratio_failures = 0

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_num += 1
                    if not row:
                        continue

                    # Pad row to enough columns
                    cells = list(row) + [None] * 15

                    # Skip header / empty rows
                    first = str(cells[0] or "").strip()
                    if not first or "BARCODE" in first.upper():
                        continue

                    # Clean barcode — strip any leaked header text
                    barcode_raw = re.sub(r"(?i)BARCODE\s*\n?", "", first)
                    barcode = re.sub(r"\D", "", barcode_raw)

                    code = str(cells[1] or "").strip()
                    name = str(cells[2] or "").strip()

                    if not name or len(name) < 3:
                        continue

                    # Category may contain pipe-separated values
                    category_raw = str(cells[6] or "").strip()
                    category = category_raw.split("|")[0].strip() if category_raw else ""

                    wh_raw = cells[9]
                    rt_raw = cells[10]

                    wholesale = _extract_xt(wh_raw)
                    retail = _extract_rt(rt_raw)

                    if wholesale is None or retail is None:
                        errors.append(ParseError(
                            filename=path.name,
                            row=row_num,
                            reason=f"Price extraction failed — XT={str(wh_raw)[:50]!r}",
                            raw=f"name={name}",
                        ))
                        logger.debug("Price extraction failed for row %d: name=%s", row_num, name)
                        continue

                    if not _valid_ratio(wholesale, retail):
                        ratio_failures += 1
                        errors.append(ParseError(
                            filename=path.name,
                            row=row_num,
                            reason=(
                                f"Price ratio {wholesale:.2f}/{retail:.2f}="
                                f"{wholesale/retail:.2f} outside [{PRICE_RATIO_MIN},{PRICE_RATIO_MAX}]"
                            ),
                            raw=f"name={name}",
                        ))
                        continue

                    products.append(ProductRecord(
                        source="viogenesis",
                        code=code,
                        name=name,
                        wholesale_price=round(wholesale, 2),
                        retail_price=round(retail, 2),
                        barcode=barcode,
                        category=category,
                    ))

    # Warn if a high fraction of rows were dropped by ratio validation —
    # this usually means the PDF format has changed and patterns need re-tuning.
    total_attempted = len(products) + ratio_failures
    if total_attempted > 0 and ratio_failures / total_attempted > PRICE_RATIO_WARN_THRESHOLD:
        pct = ratio_failures / total_attempted
        msg = (
            f"High ratio-failure rate: {ratio_failures}/{total_attempted} rows dropped "
            f"({pct:.0%}). The VioGenesis PDF format may have changed — "
            "price extraction patterns may need re-tuning."
        )
        logger.warning(msg)
        # Prepend as first error so it's prominent in the UI
        errors.insert(0, ParseError(
            filename=path.name,
            row=0,
            reason=f"⚠️ {msg}",
            raw=None,
        ))

    logger.info(
        "VioGenesis parse complete: %d products, %d errors (%d ratio failures)",
        len(products), len(errors), ratio_failures,
    )
    return products, errors
