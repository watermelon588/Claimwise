"""LLM factory: Gemini as the primary model (a second key as its spare), Groq GPT-OSS as the automatic fallback."""

from langchain_core.runnables import Runnable

from app.config import get_settings

# A hung or rate-limited provider must not hold a claim thread's lock: give up after 60 seconds and two retries,
# so the fallback model (or a 'failed' document) takes over. The SDK default for Gemini is no timeout, six retries.
TIMEOUT_S, MAX_RETRIES = 60, 2


class LLMNotConfigured(RuntimeError):
    """Raised when no provider has an API key."""


def _geminis() -> list:
    """One Gemini chat model per configured key (GOOGLE_API_KEY, then GOOGLE_API_KEY2); empty when none is set.

    Each key has its own free-tier daily quota, so the second key takes over when the first is exhausted.
    """
    s = get_settings()
    keys = [k for k in (s.google_api_key, s.google_api_key2) if k]
    if not keys:
        return []
    from langchain_google_genai import ChatGoogleGenerativeAI

    # ponytail: an exhausted key still costs its retries on every call before the next key runs; skip it for
    # the rest of the day if that latency matters.
    return [ChatGoogleGenerativeAI(model=s.gemini_model, google_api_key=k, temperature=0,
                                   timeout=TIMEOUT_S, max_retries=MAX_RETRIES) for k in keys]


def _groq():
    """Groq chat model, or None when GROQ_API_KEY is missing."""
    s = get_settings()
    if not s.groq_api_key:
        return None
    from langchain_groq import ChatGroq

    return ChatGroq(model=s.groq_model, api_key=s.groq_api_key, temperature=0,
                    request_timeout=TIMEOUT_S, max_retries=MAX_RETRIES)


def _models() -> list:
    """Configured chat models in call order: the LLM_PROVIDER models first, then the other provider's."""
    geminis, groq = _geminis(), [m for m in [_groq()] if m is not None]
    return geminis + groq if get_settings().llm_provider == "gemini" else groq + geminis


def _chain(models: list) -> Runnable:
    """First model, retried on each later model in turn when it errors."""
    return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]


def get_document_llm(schema: type) -> Runnable:
    """Model that reads PDFs and images and returns the given schema: Gemini keys only (Groq takes no files).

    Raises:
        LLMNotConfigured: if no Gemini key is set.
    """
    models = [m.with_structured_output(schema) for m in _geminis()]
    if not models:
        raise LLMNotConfigured("Reading documents needs GOOGLE_API_KEY (Gemini)")
    return _chain(models)


def get_structured_llm(schema: type) -> Runnable:
    """Chat model that returns the given Pydantic schema, with the same fallback order as get_llm.

    Raises:
        LLMNotConfigured: if no provider has an API key.
    """
    models = [m.with_structured_output(schema) for m in _models()]
    if not models:
        raise LLMNotConfigured("Set GOOGLE_API_KEY or GROQ_API_KEY")
    return _chain(models)


def get_llm(tools: list | None = None) -> Runnable:
    """Build the chat model: LLM_PROVIDER first, then its spare keys, then the other provider.

    Args:
        tools: Tools to bind; bound on each model before wrapping so every fallback knows them too.
    Returns:
        A runnable chat model; on any error it retries the call on the next model.
    Raises:
        LLMNotConfigured: if no provider has an API key.
    """
    models = _models()
    if not models:
        raise LLMNotConfigured("Set GOOGLE_API_KEY or GROQ_API_KEY")
    return _chain([m.bind_tools(tools) for m in models] if tools else models)
