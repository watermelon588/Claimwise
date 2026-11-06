"""Onboarding: missing-item rules, upload validation, and the full upload -> confirm -> role flow.

No LLM key needed: the document reader and the chat model are replaced with fakes.
"""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent import graph as graph_module
from app.agent import onboarding
from app.agent.onboarding import DocumentExtraction, PolicyFields, missing_items

PDF = b"%PDF-1.4 synthetic test file"


def _policy(status: str, members: list[str]) -> dict:
    """Minimal policy record for missing_items tests."""
    return {"doc_id": "d1", "status": status, "members": members}


def test_missing_items_rules():
    """Each required item shows up until it is satisfied."""
    assert missing_items({}) == ["policy_document", "role"]
    assert missing_items({"policies": [_policy("pending", ["Ravi Kumar"])]}) == ["policy_confirmation", "role"]
    assert missing_items({"policies": [_policy("rejected", ["Ravi Kumar"])]}) == ["policy_document", "role"]
    role = {"role": "caregiver", "patient_name": "ravi kumar", "relation": "son"}
    assert missing_items({"policies": [_policy("confirmed", ["Ravi Kumar"])], "user_role": role}) == ["authority"]
    active = {"status": "active", "expires_on": None}
    assert missing_items({"policies": [_policy("confirmed", ["Ravi Kumar"])], "user_role": role, "authority": active}) == []
    expired = {"status": "active", "expires_on": "2020-01-01"}
    assert missing_items({"policies": [_policy("confirmed", ["Ravi Kumar"])], "user_role": role, "authority": expired}) == ["authority"]
    other = {**role, "patient_name": "Sita Devi"}
    assert missing_items({"policies": [_policy("confirmed", ["Ravi Kumar"])], "user_role": other, "authority": active}) == ["patient_on_policy"]


@pytest.fixture
def client(monkeypatch, tmp_path):
    """API client with in-memory checkpoints, temp upload folder, fake reader and fake chat model."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    extraction = DocumentExtraction(
        doc_type="policy_schedule",
        policy=PolicyFields(insurer="Suraksha General (MOCK)", policy_number="P-123", members=["Ravi Kumar"], sum_insured=300000),
    )
    monkeypatch.setattr(onboarding, "extract_document", lambda doc: extraction)

    # Scripted model: first ask to record the role, then give a final reply.
    script = iter([
        AIMessage("", tool_calls=[{"name": "record_role", "id": "c1", "args": {
            "role": "caregiver", "patient_name": "Ravi Kumar", "relation": "son"}}]),
        AIMessage("All set."),
    ])

    class FakeLLM:
        def invoke(self, messages):
            return next(script)

    monkeypatch.setattr(graph_module, "get_llm", lambda tools=None: FakeLLM())
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_upload_rejects_bad_files(client):
    """Wrong type, fake PDF bytes and unsafe thread ids are refused."""
    bad_type = client.post("/api/documents", data={"thread_id": "t1"}, files={"file": ("a.txt", b"hi", "text/plain")})
    assert bad_type.status_code == 415
    fake_pdf = client.post("/api/documents", data={"thread_id": "t1"}, files={"file": ("a.pdf", b"MZ...", "application/pdf")})
    assert fake_pdf.status_code == 415
    traversal = client.post("/api/documents", data={"thread_id": "../x"}, files={"file": ("a.pdf", PDF, "application/pdf")})
    assert traversal.status_code == 422
    assert client.post("/api/resume", json={"thread_id": "t1", "approved": True}).status_code == 409


def test_upload_confirm_role_flow(client):
    """Upload pauses for confirmation; resume confirms with a correction; a caregiver role then needs authority."""
    up = client.post("/api/documents", data={"thread_id": "t2"}, files={"file": ("policy.pdf", PDF, "application/pdf")})
    body = up.json()
    assert up.status_code == 200
    assert body["pending"]["type"] == "confirm_policy"
    assert body["pending"]["policy"]["policy_number"] == "P-123"

    done = client.post("/api/resume", json={
        "thread_id": "t2", "approved": True, "corrections": {"sum_insured": 500000, "hacker_field": 1},
    }).json()
    assert done["pending"] is None
    assert done["reply"] == "All set."
    # A caregiver still has to record their authority before claim work (DEV-025).
    assert done["onboarding"] == {"complete": False, "missing": ["authority"]}

    state = client.app.state.graph.get_state({"configurable": {"thread_id": "t2"}}).values
    [policy] = state["policies"]
    assert (policy["status"], policy["sum_insured"], policy["corrected_fields"]) == ("confirmed", 500000, ["sum_insured"])
    assert state["user_role"]["relation"] == "son"


def test_non_claim_file_is_rejected_and_deleted(monkeypatch, tmp_path):
    """A random photo (classified other) is rejected, its stored file deleted, and no facts kept."""
    photo = tmp_path / "x.jpg"
    photo.write_bytes(b"\xff\xd8\xff synthetic photo")
    doc = {"id": "x", "filename": "holiday.jpg", "mime_type": "image/jpeg", "path": str(photo),
           "status": "uploaded", "doc_type": None, "error": None, "facts": None}
    monkeypatch.setattr(onboarding, "extract_document", lambda d: DocumentExtraction(doc_type="other", summary="beach"))
    [out] = onboarding.parse_new_documents({"documents": [doc]})["documents"]
    assert (out["status"], out["path"], out["facts"]) == ("rejected", "", None)
    assert not photo.exists()
    assert missing_items({"documents": [out]}) == ["policy_document", "role"]
