"""Smoke tests for the API wiring. No LLM key or database needed."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.main import app


def test_failed_upload_retry_and_permanent_deletion(monkeypatch, tmp_path):
    """Retry by button and reupload, then erase the file, checkpoint history and session."""
    from app.agent import graph, onboarding
    from app.config import get_settings

    class Model:
        """Return a reply with no document content."""

        def invoke(self, _messages):
            """Simulate the same outage on the first reply after a failed extraction."""
            if len(attempts) == 1 and next(iter(attempts.values())) == 1:
                raise RuntimeError("Synthetic reply outage")
            return AIMessage("Noted.")

    attempts = {}

    def extract(document):
        """Simulate a provider failure on the first attempt for each file."""
        doc_id = document["id"]
        attempts[doc_id] = attempts.get(doc_id, 0) + 1
        if attempts[doc_id] == 1:
            raise RuntimeError("Synthetic provider failure")
        assert Path(document["path"]).read_bytes().startswith(b"%PDF")
        return onboarding.DocumentExtraction(doc_type="hospital_bill")

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setattr(graph, "get_llm", lambda _tools: Model())
    monkeypatch.setattr(onboarding, "extract_document", extract)
    get_settings.cache_clear()

    def upload(client, thread, name, content):
        """Send a synthetic PDF through the multipart upload route."""
        return client.post("/api/documents", data={"thread_id": thread},
                           files={"file": (name, b"%PDF" + content, "application/pdf")})

    try:
        with TestClient(app) as client:
            thread = "file-controls"
            prefix = f"/api/thread/{thread}/documents"
            config = {"configurable": {"thread_id": thread}}
            first = upload(client, thread, "first.pdf", b"first").json()
            first_id = first["processed_document_id"]
            assert first["documents"][0]["status"] == "failed"
            retried = client.post(f"{prefix}/{first_id}/retry").json()
            assert retried["processed_document_id"] == first_id
            assert [d["status"] for d in retried["documents"]] == ["parsed"]
            assert sum(m["text"] == "Uploaded first.pdf" for m in retried["history"]) == 1
            assert upload(client, thread, "first.pdf", b"first").status_code == 409

            failed = upload(client, thread, "second.pdf", b"second").json()
            second_id = failed["processed_document_id"]
            resent = upload(client, thread, "renamed.pdf", b"second").json()
            assert resent["processed_document_id"] == second_id
            assert len(resent["documents"]) == 2

            other = upload(client, "other-session", "other.pdf", b"other").json()["processed_document_id"]
            deleted = client.delete(f"{prefix}/{first_id}")
            assert deleted.status_code == 200, deleted.text
            assert [d["id"] for d in deleted.json()["documents"]] == [second_id]
            assert not (tmp_path / thread / f"{first_id}.pdf").exists()
            saver = client.app.state.graph.checkpointer
            checkpoints = list(saver.list(config))
            assert checkpoints
            assert first_id not in repr(checkpoints)

            assert client.delete(f"/api/thread/{thread}").status_code == 204
            assert client.delete(f"/api/thread/{thread}").status_code == 204
            assert not list(saver.list(config))
            assert not (tmp_path / thread).exists()
            assert (tmp_path / "other-session" / f"{other}.pdf").is_file()
            assert [t["thread_id"] for t in client.get(f"/api/threads?ids={thread},other-session").json()] == ["other-session"]
    finally:
        get_settings.cache_clear()


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

def test_workspace_reads_only_approved_tools_after_onboarding(monkeypatch):
    """A verified workspace reads its approved resource and keeps fixture evidence separate from claim status."""
    from app import connector
    from app.config import get_settings
    from tests.test_claim import BILL, SUMMARY, base_state

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    tools = ["read_bank_credits", "case_email"]
    reads, mail = [], []

    def discover(case_id, thread_id):
        assert case_id == "case-connector-code" and thread_id == "workspace-test"
        return tools.copy()

    def read(case_id, tool):
        assert case_id == "case-connector-code"
        reads.append(tool)
        return {"credits": [{"amount": 4000}]}

    monkeypatch.setattr(connector, "connected_tools", discover)
    monkeypatch.setattr(connector, "read_fixture", read)
    monkeypatch.setattr(connector, "deliver_notices", lambda case_id, notices: mail.extend(notices))
    body = {"thread_id": "workspace-test", "code": "case-connector-code"}

    with TestClient(app) as client:
        assert client.post("/api/connection/sync", json=body).status_code == 409
        config = {"configurable": {"thread_id": "workspace-test"}}
        app.state.graph.update_state(config, base_state(SUMMARY, BILL), as_node="reply_off_topic")
        response = client.post("/api/connection/sync", json=body)
        assert response.status_code == 200
        assert "Credit entries: 1" in response.json()["notifications"][0]["text"]
        assert response.json()["connection"] is None
        assert response.json()["claim"].get("payment") is None
        assert len(mail) == 1 and set(mail[0]) == {"id", "at", "kind"}
        assert reads == ["read_bank_credits"]

        tools.clear()
        assert client.post("/api/connection/sync", json=body).status_code == 200
        state = app.state.graph.get_state(config).values
        assert state["workspace_connectors"]["evidence"] == {}
        assert reads == ["read_bank_credits"]
    get_settings.cache_clear()
