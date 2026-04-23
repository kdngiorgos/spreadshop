"""
Spreadshop — Shared configuration constants.
Single source of truth for all tuneable values.
Import from here rather than hardcoding magic numbers.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Price validation (wholesale / retail ratio)
# ---------------------------------------------------------------------------
PRICE_RATIO_MIN = 0.48   # minimum acceptable wholesale/retail ratio
PRICE_RATIO_MAX = 0.78   # maximum acceptable wholesale/retail ratio
# Warn in UI if more than this fraction of rows are dropped by ratio check
PRICE_RATIO_WARN_THRESHOLD = 0.05

# ---------------------------------------------------------------------------
# Analysis thresholds
# ---------------------------------------------------------------------------
MARGIN_STRONG_BUY_PCT = 30.0   # % margin required for "strong_buy" recommendation
MARGIN_CONSIDER_PCT   = 15.0   # % margin required for "consider" recommendation
SHOPS_STRONG_BUY_MAX  = 10     # max shop count to qualify for "strong_buy"
SHOPS_LOW_MAX         = 4      # ≤ this many shops → competition level "Low"
SHOPS_MEDIUM_MAX      = 15     # ≤ this many shops → competition level "Medium"

# Opportunity score weights (must sum to 100)
SCORE_MARGIN_WEIGHT      = 50
SCORE_COMPETITION_WEIGHT = 30
SCORE_DEMAND_WEIGHT      = 20

SCORE_COMPETITION_BASE = 30   # shops at or above this → 0 competition score
SCORE_DEMAND_BASE      = 100  # reviews at or above this → max demand score

# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
SCRAPER_DEFAULT_DELAY         = 1.5    # base seconds between requests
SCRAPER_DEFAULT_JITTER        = 0.5    # ± random jitter added to delay
SCRAPER_PAGE_TIMEOUT_MS       = 30000  # Request timeout (ms)
SCRAPER_FUZZY_MATCH_THRESHOLD = 0.35   # min SequenceMatcher ratio for a valid match
SCRAPER_CONCURRENCY           = 2      # max parallel async workers
SCRAPER_MAX_RETRIES           = 3      # retry attempts on 429/503 before giving up

# ---------------------------------------------------------------------------
# Runtime environment
# ---------------------------------------------------------------------------
import os

# Load .env if present (ignored by git)
def _load_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

# Set SPREADSHOP_HEADLESS=true (e.g. in Docker) to force headless Chromium.
HEADLESS_MODE: bool = os.environ.get("SPREADSHOP_HEADLESS", "false").lower() == "true"

# Scraper source: "serpapi" (default) or "skroutz" (legacy, requires curl_cffi)
SCRAPER_SOURCE: str = os.environ.get("SPREADSHOP_SCRAPER", "serpapi")
SERPAPI_KEY:    str = os.environ.get("SERPAPI_KEY", "")

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS    = 60 * 60 * 24  # 24 hours
CACHE_DIR            = "cache"
CACHE_SCHEMA_VERSION = 2             # bump when SkroutzResult fields change

# ---------------------------------------------------------------------------
# E-shop generator
# ---------------------------------------------------------------------------
ESHOP_PORT       = 8082              # local preview server port
ESHOP_OUTPUT_DIR = "eshop_output"    # directory for generated static site
