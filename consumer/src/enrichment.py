from bs4 import BeautifulSoup

from shared.logger import get_logger
from shared.scraper import fetch_position_html, parse_skills_count, parse_years_of_experience
from src.config import settings
from src.consts import CATEGORY_KEYWORDS, SENIORITY_LEVEL_KEYWORDS, SENIORITY_SCORES
from src.models import BasePosition, EnrichedPosition
from src.url_cache import get_cached_enrichment, hash_requirements_block, load_cache, save_cache

logger = get_logger(__name__)


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
    seniority_score = SENIORITY_SCORES.get(seniority_level, 0)
    return round(experience_score + skills_score + seniority_score)


def _enrich_one(
    position: BasePosition,
    cache: dict,
) -> EnrichedPosition:
    """Enrich a single BasePosition by scraping its detail page.

    Checks `cache["positions_enrichment"]` first; if the requirements block
    HTML is unchanged (same hash), returns the cached result without
    re-computing. New results are written into `cache` in memory so the
    caller can do a single disk flush after all positions are processed.
    """
    url = position.url or None

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
                        url=position.url,
                        **cached,
                    )

                years = parse_years_of_experience(req_block)
                skills = parse_skills_count(req_block)
            else:
                logger.debug("No requirements block found for: %s", position.title)
    else:
        logger.warning("No URL available for position: %s", position.title)

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
        url=position.url,
        **enrichment_fields,
    )


def enrich_positions(positions: list[BasePosition]) -> list[EnrichedPosition]:
    """Enrich a list of Positions with scraped signals and a complexity score."""
    if not positions:
        logger.warning("Received empty positions list for enrichment")
        return []

    cache: dict = load_cache(settings.url_cache_path) or {"positions_enrichment": {}}

    logger.info("Enriching %d positions", len(positions))

    enriched = [_enrich_one(p, cache) for p in positions]

    save_cache(settings.url_cache_path, cache)
    return enriched
