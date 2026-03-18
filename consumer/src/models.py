from pydantic import BaseModel


class Position(BaseModel):
    index: int
    title: str
    url: str | None = None
