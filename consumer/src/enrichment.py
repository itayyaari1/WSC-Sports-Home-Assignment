import re

import requests
from bs4 import BeautifulSoup

from shared.logger import get_logger
from src.config import settings
from src.consts import CATEGORY_KEYWORDS, SENIORITY_KEYWORDS, SENIORITY_LEVEL_KEYWORDS
from src.models import BasePosition, EnrichedPosition
from src.url_cache import get_cached_enrichment, hash_requirements_block, load_cache, save_cache

logger = get_logger(__name__)


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


def classify_category(title: str) -> str:
    """Classify a position title into a category using keyword matching."""
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "Other"


def classify_seniority_level(req_block: BeautifulSoup | None, years: int) -> str:
    """Derive Junior/Mid/Senior/Lead from the requirements block and years of experience.

    Years-of-experience thresholds are the primary signal. When years = 0,
    falls back to keyword scanning of the requirements text.
    """
    if years >= 7:
        return "Lead"
    if years >= 4:
        return "Senior"
    if years >= 1:
        return "Mid"

    # years == 0: fall back to keyword scan of the requirements text
    if req_block:
        req_text = req_block.get_text(" ", strip=True).lower()
        for level, keywords in SENIORITY_LEVEL_KEYWORDS.items():
            if any(kw in req_text for kw in keywords):
                return level

    return "Mid"


_SENIORITY_SCORES = {"Junior": 5, "Mid": 10, "Senior": 15, "Lead": 20}


def calculate_complexity_score(
    years: int,
    skills: int,
    seniority_level: str,
) -> int:
    """Calculate a 0-100 complexity score from three weighted factors.

    Experience  40%: years mapped to 0-8+ scale
    Skills      40%: li count mapped to 0-10+ scale
    Seniority   20%: graduated — Junior 5, Mid 10, Senior 15, Lead 20
    """
    experience_score = min(years / 8, 1.0) * 40
    skills_score = min(skills / 8, 1.0) * 40
    seniority_score = _SENIORITY_SCORES.get(seniority_level, 0)
    return round(experience_score + skills_score + seniority_score)


def _enrich_one(
    position: BasePosition,
    title_mapping: dict[str, str],
    cache: dict,
) -> EnrichedPosition:
    """Enrich a single BasePosition by scraping its detail page.

    Checks `cache["positions_enrichment"]` first; if the requirements block
    HTML is unchanged (same hash), returns the cached result without
    re-computing. New results are written into `cache` in memory so the
    caller can do a single disk flush after all positions are processed.
    """
    url = title_mapping.get(position.title)

    years = 0
    skills = 0
    req_block = None

    if url:
        html = fetch_position_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            req_block = soup.select_one(
                "div.career-text-block__wrp--data--requirements"
            )
            if req_block:
                req_block_html = str(req_block)
                cached = get_cached_enrichment(req_block_html, cache)
                if cached:
                    logger.debug("Enrichment cache hit for: %s", position.title)
                    return EnrichedPosition(
                        index=position.index,
                        title=position.title,
                        **cached,
                    )

                years = parse_years_of_experience(req_block)
                skills = parse_skills_count(req_block)
            else:
                logger.debug("No requirements block found for: %s", position.title)
    else:
        logger.warning("No URL found for position: %s", position.title)

    category = classify_category(position.title)
    seniority_level = classify_seniority_level(req_block, years)
    score = calculate_complexity_score(years, skills, seniority_level)

    enrichment_fields = {
        "category": category,
        "seniority_level": seniority_level,
        "years_of_experience": years,
        "skills_count": skills,
        "complexity_score": score,
    }

    if req_block is not None:
        req_hash = hash_requirements_block(str(req_block))
        cache.setdefault("positions_enrichment", {})[req_hash] = enrichment_fields

    return EnrichedPosition(
        index=position.index,
        title=position.title,
        **enrichment_fields,
    )


def enrich_positions(positions: list[BasePosition]) -> list[EnrichedPosition]:
    """Enrich a list of Positions with scraped signals and a complexity score."""
    if not positions:
        logger.warning("Received empty positions list for enrichment")
        return []

    cache: dict = load_cache(settings.url_cache_path) or {
        "page_hash": "",
        "title_mapping": {},
        "positions_enrichment": {},
    }
    title_mapping: dict[str, str] = cache.get("title_mapping", {})

    logger.info("Enriching %d positions", len(positions))

    enriched = [_enrich_one(p, title_mapping, cache) for p in positions]

    save_cache(settings.url_cache_path, cache)
    return enriched
