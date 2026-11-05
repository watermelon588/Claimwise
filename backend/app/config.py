"""Application settings loaded from environment variables or backend/.env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration.

    Attributes:
        llm_provider: Which LLM backend the agent uses.
        groq_api_key / groq_model: Groq credentials and model (GPT-OSS models are hosted there).
        google_api_key / gemini_model: Gemini credentials and model.
        database_url: Neon Postgres connection string. Empty means in-memory checkpoints.
        cors_origins: Frontend origins allowed to call the API.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["groq", "gemini"] = "gemini"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    google_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    database_url: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]
    # ponytail: local disk for the prototype; move to object storage with encryption before real users.
    upload_dir: str = "uploads"
    max_upload_mb: int = 10
    # Mock connector gateway (connectors/app.py). Empty url or key means "not connected": manual route only.
    connector_url: str = ""
    connector_agent_key: str = ""
    connector_page_url: str = "http://127.0.0.1:8101/"
    # Shared secret for the mock payer's signed webhooks; empty disables the webhook endpoint.
    mock_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
