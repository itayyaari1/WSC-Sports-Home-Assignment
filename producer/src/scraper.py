from shared.scraper import PositionScraper, ScraperError
from src.config import settings

__all__ = ["PositionScraper", "ScraperError", "make_scraper"]


def make_scraper() -> PositionScraper:
    """Factory that creates a PositionScraper from the current settings."""
    return PositionScraper(
        url=settings.careers_url,
        timeout=settings.scrape_timeout_seconds,
        retries=settings.scrape_retries,
    )
