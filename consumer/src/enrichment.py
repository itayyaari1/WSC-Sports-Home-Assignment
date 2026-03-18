import re

import requests
from bs4 import BeautifulSoup

from shared.logger import get_logger
from src.config import settings
from src.models import BasePosition, EnrichedPosition
from src.url_cache import load_cache

logger = get_logger(__name__)

SENIORITY_KEYWORDS = {"senior", "lead", "architect", "manager", "principal"}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Engineering": [
        "engineer", "developer", "devops", "backend", "frontend", "data",
        "ml", "ai", "qa", "architect", "infrastructure", "algorithm",
        "c++", "cloud", "finops", "nlp", "genai",
    ],
    "Design": [
        "design", "ux", "ui", "creative", "graphic", "motion", "visual", "animation",
    ],
    "Product": [
        "product", "program manager", "scrum", "project manager", "evangelist",
    ],
    "Operations": [
        "operations", "hr", "finance", "office", "admin", "people", "recruit",
        "sales", "account", "marketing", "business", "legal", "partnerships",
        "controller", "counsel", "bizdev",
    ],
}

_SENIORITY_LEVEL_KEYWORDS: dict[str, list[str]] = {
    "Junior": ["junior", "intern", "entry", "associate", "graduate"],
    "Senior": ["senior", "sr.", "staff"],
    "Lead": ["lead", "principal", "head", "director", "vp", "chief"],
}


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
        for level, keywords in _SENIORITY_LEVEL_KEYWORDS.items():
            if any(kw in req_text for kw in keywords):
                return level

    return "Mid"


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


def _enrich_one(position: BasePosition, title_mapping: dict[str, str]) -> EnrichedPosition:
    """Enrich a single BasePosition by scraping its detail page."""
    url = title_mapping.get(position.title)

    years = 0
    skills = 0
    has_seniority = False
    req_block = None

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

    category = classify_category(position.title)
    seniority_level = classify_seniority_level(req_block, years)
    score = calculate_complexity_score(years, skills, has_seniority)

    return EnrichedPosition(
        index=position.index,
        title=position.title,
        category=category,
        seniority_level=seniority_level,
        years_of_experience=years,
        skills_count=skills,
        complexity_score=score,
    )


def enrich_positions(positions: list[BasePosition]) -> list[EnrichedPosition]:
    """Enrich a list of Positions with scraped signals and a complexity score."""
    if not positions:
        logger.warning("Received empty positions list for enrichment")
        return []

    cache = load_cache(settings.url_cache_path)
    title_mapping: dict[str, str] = (cache or {}).get("title_mapping", {})

    logger.info("Enriching %d positions", len(positions))

    enriched = [_enrich_one(p, title_mapping) for p in positions]
    return enriched
