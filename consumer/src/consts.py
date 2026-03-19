SENIORITY_KEYWORDS: set[str] = {"senior", "lead", "architect", "manager", "principal"}

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

SENIORITY_LEVEL_KEYWORDS: dict[str, list[str]] = {
    "Junior": ["junior", "intern", "entry", "associate", "graduate"],
    "Senior": ["senior", "sr.", "staff"],
    "Lead": ["lead", "principal", "head", "director", "vp", "chief"],
}
