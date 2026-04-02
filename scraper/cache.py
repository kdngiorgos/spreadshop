from __future__ import annotations
import dataclasses
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from parsers.base import SkroutzResult
from config import CACHE_TTL_SECONDS, CACHE_DIR, CACHE_SCHEMA_VERSION

logger = logging.getLogger(__name__)


class ScrapeCache:
    def __init__(self, cache_dir: str | Path = CACHE_DIR, ttl: int = CACHE_TTL_SECONDS):
        self.path = Path(cache_dir) / "skroutz_cache.json"
        self.ttl = ttl
        self._data: dict = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cache file corrupt or unreadable (%s) — starting fresh", exc)
                self._data = {}

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    def _key(self, barcode: str, name: str) -> str:
        return barcode if barcode else name[:60].lower()

    def get(self, barcode: str, name: str) -> Optional[SkroutzResult]:
        key = self._key(barcode, name)
        entry = self._data.get(key)
        if not entry:
            return None
        # Schema version check — stale entries from old code are dropped cleanly
        if entry.get("v", 0) != CACHE_SCHEMA_VERSION:
            logger.debug("Cache entry %r has old schema version — dropping", key)
            return None
        if time.time() - entry.get("ts", 0) > self.ttl:
            return None
        try:
            d = entry["result"]
            fields = SkroutzResult.__dataclass_fields__
            kwargs = {}
            for k, f in fields.items():
                if k in d:
                    kwargs[k] = d[k]
                elif f.default is not dataclasses.MISSING:
                    kwargs[k] = f.default
                elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                    kwargs[k] = f.default_factory()  # type: ignore[misc]
                else:
                    kwargs[k] = None
            return SkroutzResult(**kwargs)
        except (KeyError, TypeError) as exc:
            logger.warning("Cache deserialization failed for key %r: %s", key, exc)
            return None

    def put(self, barcode: str, name: str, result: SkroutzResult) -> None:
        key = self._key(barcode, name)
        self._data[key] = {
            "v": CACHE_SCHEMA_VERSION,
            "ts": time.time(),
            "result": asdict(result),
        }
        self._save()
        logger.debug("Cached result for key %r (found=%s)", key, result.found)

    def has(self, barcode: str, name: str) -> bool:
        return self.get(barcode, name) is not None

    def clear(self) -> None:
        self._data = {}
        self._save()
        logger.info("Cache cleared")

    @property
    def size(self) -> int:
        return len(self._data)
