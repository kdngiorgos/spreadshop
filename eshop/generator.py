"""
Spreadshop E-shop Generator.

Takes a list of ProductAnalysis objects and renders a complete static HTML
e-shop site into output_dir using Jinja2 templates + Tailwind CSS.

Usage:
    from eshop import generate_eshop
    output_path = generate_eshop(analyses, Path("eshop_output"), site_config)
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from analysis.compare import ProductAnalysis

from .site_config import category_tint

# ---------------------------------------------------------------------------
# Jinja2 environment (lazy import — Jinja2 is a Streamlit transitive dep)
# ---------------------------------------------------------------------------
def _make_env(template: str = "t1"):
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent / "templates" / template
    if not templates_dir.exists():
        raise ValueError(f"Unknown template '{template}'. Available: t1, t2, t3.")
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )
    return env


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------
def _slugify(text: str, fallback: str = "") -> str:
    """Convert a product name to a URL-safe slug.

    Greek characters are stripped via ASCII normalization; the barcode/code
    is used as a fallback if the result is empty.
    """
    # Normalize unicode → decompose accents
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    # Keep letters, digits, spaces, hyphens
    cleaned = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", cleaned)[:60].strip("-")
    if slug:
        return slug
    # Fallback: barcode / code (alphanumeric only)
    fb = re.sub(r"[^\w]", "", fallback)[:30]
    return fb or "product"


def _unique_slugs(products: list[dict]) -> list[dict]:
    """Ensure all product dicts have a unique .slug value."""
    seen: Counter = Counter()
    for p in products:
        base = p["slug"]
        seen[base] += 1
    # Reset and re-assign with suffix only when duplicates exist
    counts: Counter = Counter()
    for p in products:
        base = p["slug"]
        counts[base] += 1
        if seen[base] > 1:
            p["slug"] = f"{base}-{counts[base]}"
    return products


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def generate_eshop(
    analyses: list["ProductAnalysis"],
    output_dir: Path,
    site_config: dict,
    template: str = "t1",
) -> Path:
    """Render a complete static e-shop site to output_dir.

    Args:
        analyses:    List of ProductAnalysis objects to include.
        output_dir:  Destination directory (created/cleared automatically).
        site_config: Dict from eshop.site_config.default_site_config().
        template:    Template variant — "t1" (Modern), "t2" (Elevate), "t3" (Market).

    Returns:
        output_dir (Path) for convenience.
    """
    output_dir = Path(output_dir)

    # ── 1. Clear / create output directory ──────────────────────
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    (output_dir / "product").mkdir()

    # ── 2. Copy static assets ────────────────────────────────────
    static_src = Path(__file__).parent / "static"
    static_dst = output_dir / "static"
    shutil.copytree(static_src, static_dst)

    # Write logo if provided
    logo_bytes = site_config.pop("logo_bytes", None)
    logo_ext   = site_config.pop("logo_ext", "png")
    if logo_bytes:
        logo_filename = f"logo.{logo_ext}"
        (static_dst / logo_filename).write_bytes(logo_bytes)
        site_config["logo_url"] = logo_filename   # relative to static/
    else:
        site_config["logo_url"] = ""

    # ── 3. Build product context dicts ───────────────────────────
    products: list[dict] = []
    for a in analyses:
        p, s = a.product, a.skroutz
        cat = (p.category or "Γενικά").strip() or "Γενικά"
        slug = _slugify(p.name, fallback=str(p.barcode or p.code or ""))
        products.append({
            "id":         p.barcode or p.code or slug,
            "name":       p.name,
            "category":   cat,
            "price":      s.lowest_price if s.found and s.lowest_price else p.retail_price,
            "cost":       p.wholesale_price,
            "margin_pct": a.margin_pct if s.found else 0.0,
            "skroutz_url": s.product_url if s.found and s.product_url else "",
            "signal":     a.recommendation,
            "slug":       slug,
            "bg_color":   category_tint(cat),
            "image_url":  s.image_url if s.found and s.image_url else "",
        })

    products = _unique_slugs(products)

    # ── 4. Build category list ───────────────────────────────────
    cat_counts: Counter = Counter(p["category"] for p in products)
    categories = sorted(
        [{"name": k, "count": v} for k, v in cat_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    # ── 5. Shared template context ───────────────────────────────
    year = datetime.date.today().year
    base_ctx = {
        "site":           site_config,
        "product_count":  len(products),
        "category_count": len(categories),
        "year":           year,
    }

    env = _make_env(template)

    # ── 6. Render index.html ─────────────────────────────────────
    index_tpl = env.get_template("index.html.j2")
    index_html = index_tpl.render(
        **base_ctx,
        products=products,
        categories=categories,
        static_root="static",
        store_root="index.html",
    )
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── 7. Render individual product pages ───────────────────────
    product_tpl = env.get_template("product.html.j2")
    for prod in products:
        product_html = product_tpl.render(
            **base_ctx,
            product=prod,
            static_root="../static",
            store_root="../index.html",
        )
        (output_dir / "product" / f"{prod['slug']}.html").write_text(
            product_html, encoding="utf-8"
        )

    # ── 8. Write site_config.json (for future hosting step) ──────
    meta = {
        "generated_at": datetime.datetime.now().isoformat(),
        "product_count": len(products),
        "category_count": len(categories),
        "template": template,
        "site": site_config,
    }
    (output_dir / "site_config.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return output_dir
