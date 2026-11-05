"""Shared test setup: no test may call a real model or connector over the network."""

import pytest

from app.agent import intent


@pytest.fixture(autouse=True)
def no_real_intent_model(monkeypatch):
    """I1 treats every typed message as a claim message unless a test patches classify itself."""
    monkeypatch.setattr(intent, "classify", lambda text: "claim")
