import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.careers_html import extract_title_from_link, fetch_careers_page
from shared.logger import get_logger

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

    def _base_url(self) -> str:
        parsed = urlparse(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _parse_positions(self, html: str) -> list[tuple[str, str]]:
        """Extract (title, url) pairs from the careers page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        base = self._base_url()
        positions: list[tuple[str, str]] = []

        career_links = soup.find_all("a", href=lambda h: h and "/career/" in h.lower())
        for link in career_links:
            title = extract_title_from_link(link)
            if title and title.lower() != "view position":
                href = link.get("href", "")
                url = urljoin(base, href) if not href.startswith("http") else href
                positions.append((title, url))

        if not positions:
            logger.warning("Primary selector found no positions, trying fallback strategy")
            for li in soup.find_all("li"):
                link = li.find("a")
                if link and link.get("href", ""):
                    title = extract_title_from_link(link)
                    if title and title.lower() != "view position":
                        href = link.get("href", "")
                        url = urljoin(base, href) if not href.startswith("http") else href
                        positions.append((title, url))

        return positions

    def scrape(self) -> list[tuple[str, str]]:
        """Scrape and return sorted (title, url) pairs."""
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

        positions.sort(key=lambda p: p[0].lower())

        logger.info("Found %d positions", len(positions))
        return positions


def fetch_position_html(url: str) -> str | None:
    """Fetch the HTML for a single career position page. Returns None on failure."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning("Failed to fetch position page %s: %s", url, e)
        return None


def parse_years_of_experience(req_block: BeautifulSoup) -> int:
    """Extract the maximum years-of-experience figure from the requirements block."""
    text = req_block.get_text(" ", strip=True)
    matches = re.findall(r"(\d+)\+?\s*years", text, re.IGNORECASE)
    if not matches:
        return 0
    return max(int(m) for m in matches)


def parse_skills_count(req_block: BeautifulSoup) -> int:
    """Count the number of <li> items inside the requirements block."""
    return len(req_block.find_all("li"))


def detect_seniority_keyword(soup: BeautifulSoup, seniority_keywords: list[str]) -> bool:
    """Return True if the <h1> title contains a seniority keyword."""
    h1 = soup.select_one("h1")
    if not h1:
        return False
    title_lower = h1.get_text(" ", strip=True).lower()
    return any(kw in title_lower for kw in seniority_keywords)
