import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from shared.logger import get_logger
from src.config import settings
from src.models import EnrichedPosition, Position
from src.url_cache import load_cache

logger = get_logger(__name__)

SENIORITY_KEYWORDS = {"senior", "lead", "architect", "manager", "principal"}


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


def detect_seniority_keyword(soup: BeautifulSoup) -> bool:
    """Return True if the <h1> title contains a seniority keyword."""
    h1 = soup.select_one("h1")
    if not h1:
        return False
    title_lower = h1.get_text(" ", strip=True).lower()
    return any(kw in title_lower for kw in SENIORITY_KEYWORDS)


def calculate_complexity_score(
    years: int,
    skills: int,
    has_seniority: bool,
) -> int:
    """Calculate a 0-100 complexity score from three weighted factors.

    Experience  40%: years mapped to 0-8+ scale
    Skills      40%: li count mapped to 0-10+ scale
    Seniority   20%: binary — keyword present or not
    """
    experience_score = min(years / 8, 1.0) * 40
    skills_score = min(skills / 10, 1.0) * 40
    seniority_score = 20 if has_seniority else 0
    return round(experience_score + skills_score + seniority_score)


def _enrich_one(position: Position, title_mapping: dict[str, str]) -> EnrichedPosition:
    """Enrich a single Position by scraping its detail page."""
    url = position.url or title_mapping.get(position.title)

    years = 0
    skills = 0
    has_seniority = False

    if url:
        html = fetch_position_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            req_block = soup.select_one(
                "div.career-text-block__wrp--data--requirements"
            )
            if req_block:
                years = parse_years_of_experience(req_block)
                skills = parse_skills_count(req_block)
            else:
                logger.debug("No requirements block found for: %s", position.title)
            has_seniority = detect_seniority_keyword(soup)
    else:
        logger.warning("No URL found for position: %s", position.title)

    score = calculate_complexity_score(years, skills, has_seniority)

    return EnrichedPosition(
        index=position.index,
        title=position.title,
        url=url,
        years_of_experience=years,
        required_skills_count=skills,
        has_seniority_keyword=has_seniority,
        complexity_score=score,
        enriched_at=datetime.now(timezone.utc),
    )


def enrich_positions(positions: list[Position]) -> list[EnrichedPosition]:
    """Enrich a list of Positions with scraped signals and a complexity score."""
    if not positions:
        logger.warning("Received empty positions list for enrichment")
        return []

    cache = load_cache(settings.url_cache_path)
    title_mapping: dict[str, str] = (cache or {}).get("title_mapping", {})

    logger.info("Enriching %d positions", len(positions))

    enriched = [_enrich_one(p, title_mapping) for p in positions]
    return enriched
