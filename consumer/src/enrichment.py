from shared.logger import get_logger
from datetime import datetime, timezone

import pandas as pd

logger = get_logger(__name__)

# Category keyword mappings (checked in priority order)
CATEGORY_KEYWORDS = {
    "Engineering": [
        "engineer", "developer", "devops", "sre", "backend", "frontend",
        "fullstack", "full-stack", "data", "ml", "ai", "qa", "test",
        "security", "architect", "infrastructure", "platform", "software",
        "algorithm", "c++", "cloud", "finops", "nlp", "genai",
    ],
    "Design": [
        "design", "ux", "ui", "creative", "after effects", "graphic",
        "motion", "visual", "animation",
    ],
    "Product": [
        "product", "program manager", "scrum", "agile", "project manager",
        "evangelist",
    ],
    "Operations": [
        "operations", "hr", "finance", "office", "admin", "people",
        "recruit", "sales", "account", "marketing", "business", "legal",
        "partnerships", "controller", "counsel", "bizdev",
    ],
}

# Seniority keyword mappings (checked in priority order)
SENIORITY_KEYWORDS = {
    "Lead": [
        "lead", "head", "director", "vp", "principal", "chief", "team lead",
    ],
    "Senior": ["senior", "sr.", "staff"],
    "Junior": ["junior", "jr.", "intern", "entry", "associate", "graduate"],
}

# Complexity score weights
SENIORITY_SCORES = {"Junior": 10, "Mid": 20, "Senior": 30, "Lead": 40}
CATEGORY_SCORES = {
    "Engineering": 30,
    "Design": 20,
    "Product": 20,
    "Operations": 15,
    "Other": 10,
}
COMPLEXITY_KEYWORDS = ["architect", "fullstack", "full-stack", "principal"]


def classify_category(title: str) -> str:
    """Classify a position title into a category."""
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "Other"


def detect_seniority(title: str) -> str:
    """Detect seniority level from a position title."""
    title_lower = title.lower()
    for level, keywords in SENIORITY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return level
    return "Mid"


def calculate_complexity(title: str, category: str, seniority: str) -> int:
    """Calculate a complexity score (0-100) based on title, category, and seniority."""
    score = 0

    # Seniority weight (0-40)
    score += SENIORITY_SCORES.get(seniority, 20)

    # Category tech depth (0-30)
    score += CATEGORY_SCORES.get(category, 10)

    # Title specificity based on word count (0-15)
    word_count = len(title.split())
    specificity = min(word_count * 3, 15)
    score += specificity

    # Keyword modifiers (0-15)
    title_lower = title.lower()
    modifier_score = sum(5 for kw in COMPLEXITY_KEYWORDS if kw in title_lower)
    score += min(modifier_score, 15)

    return min(score, 100)


def enrich_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich a positions DataFrame with category, seniority, and complexity score."""
    if df.empty:
        logger.warning("Received empty DataFrame for enrichment")
        df["category"] = pd.Series(dtype="str")
        df["seniority_level"] = pd.Series(dtype="str")
        df["complexity_score"] = pd.Series(dtype="int32")
        df["enriched_at"] = pd.Series(dtype="datetime64[ns, UTC]")
        return df

    logger.info("Enriching %d positions", len(df))

    df["category"] = df["Position_Title"].apply(classify_category)
    df["seniority_level"] = df["Position_Title"].apply(detect_seniority)
    df["complexity_score"] = df.apply(
        lambda row: calculate_complexity(
            row["Position_Title"], row["category"], row["seniority_level"]
        ),
        axis=1,
    ).astype("int32")
    df["enriched_at"] = datetime.now(timezone.utc)

    logger.info("Enrichment complete. Categories: %s", df["category"].value_counts().to_dict())
    return df
