"""Configuration settings for Claimwise mock services."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Mock application configuration loaded from environment variables."""

    mock_port: int = 8100
    mock_api_keys: str = "claimwise-demo-key,hospital-demo-key"
    mock_webhook_secret: str = "mock-secret-key-12345"
    claimwise_webhook_url: str = "http://localhost:8000/api/webhooks/mock"
    mock_db_path: str = "mock.db"
    docs_storage_path: str = "generated_docs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def api_keys_list(self) -> list[str]:
        """Return allowed API keys as a parsed list."""
        return [k.strip() for k in self.mock_api_keys.split(",") if k.strip()]


settings = Settings()
