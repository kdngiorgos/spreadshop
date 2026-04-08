from .cache import ScrapeCache


def get_scraper(source: str = "serpapi", **kwargs):
    """Factory — returns the appropriate scraper without eager imports."""
    if source == "serpapi":
        from .serpapi_client import SerpApiScraper
        return SerpApiScraper(**kwargs)
    if source == "skroutz":
        from .skroutz import SkroutzScraper
        return SkroutzScraper(**kwargs)
    raise ValueError(f"Unknown scraper source: {source!r}")


__all__ = ["ScrapeCache", "get_scraper"]
