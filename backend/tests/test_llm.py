"""LLM factory order: both Gemini keys before Groq. Builds models with fake keys; never calls a provider."""

from pydantic import BaseModel

from app.agent import llm
from app.config import Settings


class _Out(BaseModel):
    """Placeholder schema for the structured-output chain."""

    ok: bool


def _use(monkeypatch, **values) -> None:
    """Point the factory at settings built only from the given values (no .env, no real keys)."""
    base = {"llm_provider": "gemini", "google_api_key": "", "google_api_key2": "", "groq_api_key": ""}
    settings = Settings(_env_file=None, **{**base, **values})
    monkeypatch.setattr(llm, "get_settings", lambda: settings)


def test_second_gemini_key_is_tried_before_groq(monkeypatch):
    """Chat order is key 1, key 2, then Groq."""
    _use(monkeypatch, google_api_key="fake-1", google_api_key2="fake-2", groq_api_key="fake-g")
    chain = llm.get_llm()
    models = [chain.runnable, *chain.fallbacks]
    assert [type(m).__name__ for m in models] == ["ChatGoogleGenerativeAI", "ChatGoogleGenerativeAI", "ChatGroq"]
    assert [m.google_api_key.get_secret_value() for m in models[:2]] == ["fake-1", "fake-2"]


def test_document_reading_falls_back_to_the_second_key(monkeypatch):
    """Document reading has no Groq fallback, so the spare key is its only fallback."""
    _use(monkeypatch, google_api_key="fake-1", google_api_key2="fake-2")
    assert len(llm.get_document_llm(_Out).fallbacks) == 1


def test_one_key_still_works(monkeypatch):
    """Without the second key the document model is a single model, not a fallback chain."""
    _use(monkeypatch, google_api_key="fake-1")
    assert not hasattr(llm.get_document_llm(_Out), "fallbacks")
