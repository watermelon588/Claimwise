"""Smoke tests for the API wiring. No LLM key or database needed."""

import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.main import app


def test_health_and_chat_without_llm_key(monkeypatch):
    """Health reports in-memory DB; chat returns 503 when no LLM key is set."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY2", "")
    from app.config import get_settings

    get_settings.cache_clear()  # re-read env set above

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health == {"status": "ok", "database": "memory", "llm_provider": "groq"}

        resp = client.post("/api/chat", json={"thread_id": "t1", "message": "hi"})
        assert resp.status_code == 503
        assert "API_KEY" in resp.json()["detail"]


def test_chat_stream_without_llm_key(monkeypatch):
    """chat/stream yields an error event when no LLM key is set."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY2", "")
    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as client:
        resp = client.post("/api/chat/stream", json={"thread_id": "t1", "message": "hi"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "error" in resp.text


def test_chat_stream_emits_activity_for_actual_tool_node(monkeypatch):
    """Observe tool start and finish on a real graph without leaking its inputs."""
    from app.agent import graph
    from app.config import get_settings

    class ToolCallingModel:
        """Request one deterministic tool and then reply when its result arrives."""

        def invoke(self, messages):
            """Return a tool request on the first turn and a plain reply afterward."""
            if isinstance(messages[-1], ToolMessage):
                return AIMessage(content="The check is complete.")
            return AIMessage(content="", tool_calls=[{
                "name": "claim_deadline",
                "args": {"event": "claim_submitted", "event_date": "2026-11-05"},
                "id": "call-1",
            }])

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(graph, "get_llm", lambda _tools: ToolCallingModel())
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.post("/api/chat/stream", json={"thread_id": "activity", "message": "Check my date"})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    assert [event for event in events if event["type"] == "activity"] == [
        {"type": "activity", "state": "tool"},
        {"type": "activity", "state": "thinking"},
    ]
    assert events[-1]["type"] == "done"
    assert events[-1]["reply"] == "The check is complete."


def test_unexpected_graph_exception_returns_json_500(monkeypatch):
    """Unexpected graph/DB errors return structured JSON 500 instead of plain text."""
    from app.agent import graph
    from app.config import get_settings

    class BrokenModel:
        """Simulate a dropped DB connection or runtime error inside graph execution."""

        def invoke(self, _messages):
            raise RuntimeError("SSL SYSCALL error: EOF detected")

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(graph, "get_llm", lambda _tools: BrokenModel())
    get_settings.cache_clear()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/api/chat", json={"thread_id": "t-err", "message": "hi"})
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert "RuntimeError" in body["detail"]
        assert "Please try again" in body["detail"]


def test_threads_list_and_thread_state_hydration(monkeypatch):
    """GET /api/threads and GET /api/thread/{thread_id} return session summaries and answers."""
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()

    with TestClient(app) as client:
        threads_resp = client.get("/api/threads")
        assert threads_resp.status_code == 200
        assert threads_resp.json() == []

        snap_resp = client.get("/api/thread/test-thread-001")
        assert snap_resp.status_code == 200
        payload = snap_resp.json()
        assert "history" in payload
        assert "answers" in payload
        assert isinstance(payload["answers"], dict)
        assert payload["documents"] == []
