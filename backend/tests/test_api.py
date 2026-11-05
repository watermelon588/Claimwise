"""Smoke tests for the API wiring. No LLM key or database needed."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_chat_without_llm_key(monkeypatch):
    """Health reports in-memory DB; chat returns 503 when no LLM key is set."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()  # re-read env set above

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health == {"status": "ok", "database": "memory", "llm_provider": "groq"}

        resp = client.post("/api/chat", json={"thread_id": "t1", "message": "hi"})
        assert resp.status_code == 503
        assert "API_KEY" in resp.json()["detail"]
