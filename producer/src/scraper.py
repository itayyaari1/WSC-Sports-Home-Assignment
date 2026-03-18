import logging
import unicodedata

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when scraping fails after all retries."""


@retry(
    stop=stop_after_attempt(settings.scrape_retries),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
    before_sleep=lambda retry_state: logger.warning(
        "Scrape attempt %d failed, retrying...", retry_state.attempt_number
    ),
)
def fetch_page(url: str) -> str:
    """Fetch the careers page HTML content."""
    response = requests.get(url, timeout=settings.scrape_timeout_seconds)
    response.raise_for_status()
    return response.text


def normalize_title(title: str) -> str:
    """Strip whitespace and normalize unicode characters."""
    title = title.strip()
    title = unicodedata.normalize("NFKD", title)
    # Collapse multiple whitespace into single space
    title = " ".join(title.split())
    return title


def parse_positions(html: str) -> list[str]:
    """Extract position titles from the careers page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    positions = []

    # Primary strategy: find links containing "/career/" in href
    career_links = soup.find_all("a", href=lambda h: h and "/career/" in h.lower())
    for link in career_links:
        # The first div inside the link contains the job title
        title_div = link.find("div")
        if title_div:
            title = normalize_title(title_div.get_text())
            if title and title.lower() != "view position":
                positions.append(title)

    # Fallback: if no positions found with primary strategy, try broader search
    if not positions:
        logger.warning("Primary selector found no positions, trying fallback strategy")
        for li in soup.find_all("li"):
            link = li.find("a")
            if link and link.get("href", ""):
                divs = link.find_all("div")
                if len(divs) >= 1:
                    title = normalize_title(divs[0].get_text())
                    if title and title.lower() != "view position":
                        positions.append(title)

    return positions


def scrape_positions() -> list[str]:
    """Scrape, deduplicate-aware, and return sorted position titles."""
    logger.info("Scraping positions from %s", settings.careers_url)

    try:
        html = fetch_page(settings.careers_url)
    except Exception as e:
        raise ScraperError(f"Failed to fetch careers page after retries: {e}") from e

    positions = parse_positions(html)

    if not positions:
        raise ScraperError(
            "No positions found on careers page. The page structure may have changed."
        )

    # Sort alphabetically (A-Z) as required
    positions.sort(key=str.lower)

    logger.info("Found %d positions", len(positions))
    return positions
