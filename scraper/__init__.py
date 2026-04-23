from .cache import ScrapeCache


def get_scraper(source: str = "serpapi", **kwargs):
    """Factory — returns the appropriate scraper without eager imports."""
    if source == "serpapi" and not kwargs.get("api_key"):
        _warn = kwargs.get("on_status") or (lambda _: None)
        _warn("[WARN] No SerpAPI key set — falling back to Skroutz scraper.")
        source = "skroutz"
    if source == "serpapi":
        from .serpapi_client import SerpApiScraper
        return SerpApiScraper(**kwargs)
    if source == "skroutz":
        from .skroutz import SkroutzScraper
        kwargs.pop("api_key", None)   # SkroutzScraper needs no API key
        return SkroutzScraper(**kwargs)
    raise ValueError(f"Unknown scraper source: {source!r}")


__all__ = ["ScrapeCache", "get_scraper"]
