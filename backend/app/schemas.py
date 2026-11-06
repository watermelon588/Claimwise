"""Pydantic request and response models for the HTTP API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """A user message sent to one conversation thread."""

    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    """The agent's reply for that thread."""

    thread_id: str
    reply: str


class HealthResponse(BaseModel):
    """Service status: database is 'ok', 'memory' or an error string."""

    status: str
    database: str
    llm_provider: str
