"""
Spreadshop — Module-level e-shop server state buffer.

Same pattern as scrape_buffer.py: imported modules survive Streamlit reruns,
so the HTTPServer instance lives here rather than in session_state.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import http.server

# Running HTTPServer instance (or None when stopped)
server: Optional[http.server.HTTPServer] = None

# Output directory the server is currently serving
output_dir: Optional[Path] = None
