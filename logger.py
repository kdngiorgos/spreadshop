"""
Spreadshop — Logging setup.
Call setup_logging() once at app startup; all modules then use
logging.getLogger(__name__) to get a named logger.
"""
from __future__ import annotations
import logging
from pathlib import Path


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> None:
    """Configure rotating file + console logging.

    Safe to call multiple times (guards against duplicate handlers on
    Streamlit hot-reloads).
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / "spreadshop.log"

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — DEBUG and above
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    # Console handler — WARNING and above (less noise in Streamlit terminal)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.WARNING)

    root.addHandler(fh)
    root.addHandler(ch)
    root.setLevel(level)
