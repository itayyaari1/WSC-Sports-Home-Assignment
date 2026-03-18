from datetime import datetime

from pydantic import BaseModel


class Position(BaseModel):
    index: int
    title: str
    url: str | None = None


class EnrichedPosition(BaseModel):
    index: int
    title: str
    url: str | None
    years_of_experience: int
    required_skills_count: int
    has_seniority_keyword: bool
    complexity_score: int
    enriched_at: datetime
