"""LLM factory: Gemini as the primary model, Groq GPT-OSS as the automatic fallback."""

from langchain_core.runnables import Runnable

from app.config import get_settings


class LLMNotConfigured(RuntimeError):
    """Raised when no provider has an API key."""


def _gemini():
    """Gemini chat model, or None when GOOGLE_API_KEY is missing."""
    s = get_settings()
    if not s.google_api_key:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=s.gemini_model, google_api_key=s.google_api_key, temperature=0)


def _groq():
    """Groq chat model, or None when GROQ_API_KEY is missing."""
    s = get_settings()
    if not s.groq_api_key:
        return None
    from langchain_groq import ChatGroq

    return ChatGroq(model=s.groq_model, api_key=s.groq_api_key, temperature=0)


def get_llm(tools: list | None = None) -> Runnable:
    """Build the chat model: LLM_PROVIDER is the primary, the other provider is the fallback.

    Args:
        tools: Tools to bind; bound on each model before wrapping so the fallback knows them too.
    Returns:
        A runnable chat model; on any primary error it retries the call on the fallback.
    Raises:
        LLMNotConfigured: if neither provider has an API key.
    """
    gemini, groq = _gemini(), _groq()
    primary, backup = (gemini, groq) if get_settings().llm_provider == "gemini" else (groq, gemini)
    if primary is None:
        primary, backup = backup, None
    if primary is None:
        raise LLMNotConfigured("Set GOOGLE_API_KEY or GROQ_API_KEY")
    if tools:
        primary = primary.bind_tools(tools)
        backup = backup.bind_tools(tools) if backup else None
    return primary.with_fallbacks([backup]) if backup else primary
