from pydantic import BaseModel


class BasePosition(BaseModel):
    index: int
    title: str
    url: str


class EnrichedPosition(BasePosition):
    category: str
    seniority_level: str
    years_of_experience: int
    skills_count: int
    complexity_score: int
