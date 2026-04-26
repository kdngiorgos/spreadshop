"""Import-sanity tests — catches signature drift across module boundaries."""


def test_runner_imports():
    from scraper.runner import run_scrape  # noqa: F401


def test_get_scraper_factory_imports():
    from scraper import get_scraper  # noqa: F401


def test_analyze_imports():
    from analysis.compare import analyze, ProductAnalysis  # noqa: F401


def test_eshop_generator_imports():
    from eshop.generator import generate_eshop, _slugify  # noqa: F401
