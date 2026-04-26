"""
Spreadshop E-shop — Site configuration defaults and color scheme registry.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Accent color schemes
# ---------------------------------------------------------------------------
COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "green": {
        "label":       "Πράσινο",
        "accent_color": "#10B981",
        "accent_dark":  "#065F46",
    },
    "blue": {
        "label":       "Μπλε",
        "accent_color": "#3B82F6",
        "accent_dark":  "#1D4ED8",
    },
    "purple": {
        "label":       "Μοβ",
        "accent_color": "#8B5CF6",
        "accent_dark":  "#5B21B6",
    },
    "orange": {
        "label":       "Πορτοκαλί",
        "accent_color": "#F59E0B",
        "accent_dark":  "#B45309",
    },
    "red": {
        "label":       "Κόκκινο",
        "accent_color": "#EF4444",
        "accent_dark":  "#B91C1C",
    },
}

# Per-category background gradient tints (used on product image area).
# Assigned deterministically by category hash so the grid looks varied.
_CATEGORY_TINTS = [
    "#6366f1",  # indigo
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#3b82f6",  # blue
    "#ec4899",  # pink
    "#8b5cf6",  # violet
    "#14b8a6",  # teal
    "#f97316",  # orange
    "#06b6d4",  # cyan
    "#84cc16",  # lime
]


def category_tint(category: str) -> str:
    """Return a stable hex tint for the given category string."""
    return _CATEGORY_TINTS[hash(category) % len(_CATEGORY_TINTS)]


# ---------------------------------------------------------------------------
# Font pairings
# ---------------------------------------------------------------------------
FONT_OPTIONS: dict[str, dict[str, str]] = {
    "modern": {
        "label":   "Modern (DM Sans)",
        "import":  "DM+Sans:wght@400;500;600;700",
        "family":  "'DM Sans', system-ui, sans-serif",
    },
    "classic": {
        "label":   "Classic (Playfair Display)",
        "import":  "Playfair+Display:wght@400;700",
        "family":  "'Playfair Display', Georgia, serif",
    },
    "corporate": {
        "label":   "Corporate (Inter)",
        "import":  "Inter:wght@400;500;600;700",
        "family":  "'Inter', system-ui, sans-serif",
    },
    "hellenic": {
        "label":   "Hellenic (DM Serif Display + Manrope)",
        "import":  "DM+Serif+Display&family=Manrope:wght@400;500;600;700;800",
        "family":  "'Manrope', 'Noto Sans', system-ui, sans-serif",
    },
}


def default_site_config(
    store_name: str = "My Shop",
    color_scheme: str = "green",
    tagline: str = "",
    headline: str = "",
    subheadline: str = "",
    font: str = "modern",
) -> dict:
    scheme = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["green"])
    font_cfg = FONT_OPTIONS.get(font, FONT_OPTIONS["modern"])
    return {
        "name":         store_name,
        "tagline":      tagline      or "Ποιοτικά προϊόντα σε ανταγωνιστικές τιμές",
        "headline":     headline     or "Ποιοτικά προϊόντα\nγια κάθε ανάγκη.",
        "subheadline":  subheadline  or (
                            "Επιλεγμένα προϊόντα από αξιόπιστους προμηθευτές. "
                            "Γρήγορη αποστολή σε όλη την Ελλάδα."
                        ),
        "accent_color": scheme["accent_color"],
        "accent_dark":  scheme["accent_dark"],
        "currency":     "€",
        "font_import":  font_cfg["import"],
        "font_family":  font_cfg["family"],
        "logo_url":     "",   # overwritten by generator if logo_bytes provided
    }
