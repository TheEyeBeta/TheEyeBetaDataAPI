"""Chat request/response schemas."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming user chat request."""

    question: str = Field(min_length=1, max_length=1000)
    ticker: str | None = Field(default=None, max_length=16)


class ChatResponse(BaseModel):
    """AI answer response payload."""

    answer: str
    used_ticker: str | None = None
    context_rows: int = 0
