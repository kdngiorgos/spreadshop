"""
Spreadshop — Module-level scrape state buffer.

Streamlit re-executes app.py from top to bottom on every interaction, which
would reset any module-level variable defined there.  Variables in *imported*
modules are NOT reset between reruns (Python's module cache keeps them alive).

This module is the shared memory between the background scrape thread and the
Streamlit main thread.  The thread writes here; the UI reads from here.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from scraper.skroutz import SkroutzScraper

# --- mutable state ---
running: bool        = False
log: list            = []
progress: int        = 0
total: int           = 0
status: str          = ""
counts: dict         = {"found": 0, "not_found": 0, "cached": 0, "errors": 0}
results: dict        = {}   # barcode/name key → SkroutzResult
scraped_at           = None  # datetime | None
analyses_ready: bool = False  # True when thread finishes; cleared by UI after pickup
scraper              = None   # SkroutzScraper instance while running, else None
