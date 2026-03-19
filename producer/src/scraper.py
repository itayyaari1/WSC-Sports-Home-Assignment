import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.careers_html import normalize_title, strip_view_position_suffix, extract_title_from_link, fetch_careers_page
from shared.logger import get_logger
from src.config import settings

logger = get_logger(__name__)


class ScraperError(Exception):
    """Raised when scraping fails after all retries."""


class PositionScraper:
    """Scrapes job positions from the WSC Sports careers page."""

    def __init__(self, url: str, timeout: int, retries: int) -> None:
        self.url = url
        self.timeout = timeout
        self.retries = retries

    def _make_fetch(self):
        """Build and return a retry-decorated fetch callable bound to this instance."""
        @retry(
            stop=stop_after_attempt(self.retries),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
            before_sleep=lambda retry_state: logger.warning(
                "Scrape attempt %d failed, retrying...", retry_state.attempt_number
            ),
        )
        def _fetch() -> str:
            return fetch_careers_page(self.url, timeout=self.timeout)

        return _fetch

    def _fetch_page(self) -> str:
        """Fetch the careers page HTML content with retry logic."""
        return self._make_fetch()()

    def _parse_positions(self, html: str) -> list[str]:
        """Extract position titles from the careers page HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        positions = []

        career_links = soup.find_all("a", href=lambda h: h and "/career/" in h.lower())
        for link in career_links:
            title = extract_title_from_link(link)
            if title and title.lower() != "view position":
                positions.append(title)

        if not positions:
            logger.warning("Primary selector found no positions, trying fallback strategy")
            for li in soup.find_all("li"):
                link = li.find("a")
                if link and link.get("href", ""):
                    title = extract_title_from_link(link)
                    if title and title.lower() != "view position":
                        positions.append(title)

        return positions

    def scrape(self) -> list[str]:
        """Scrape, deduplicate-aware, and return sorted position titles."""
        logger.info("Scraping positions from %s", self.url)

        try:
            html = self._fetch_page()
        except Exception as e:
            raise ScraperError(f"Failed to fetch careers page after retries: {e}") from e

        positions = self._parse_positions(html)

        if not positions:
            raise ScraperError(
                "No positions found on careers page. The page structure may have changed."
            )

        positions.sort(key=str.lower)

        logger.info("Found %d positions", len(positions))
        return positions


def make_scraper() -> PositionScraper:
    """Factory that creates a PositionScraper from the current settings."""
    return PositionScraper(
        url=settings.careers_url,
        timeout=settings.scrape_timeout_seconds,
        retries=settings.scrape_retries,
    )
