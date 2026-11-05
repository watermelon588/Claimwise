"""Claim review (C1) rules and the submission approval pause. No LLM key needed."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent import graph as graph_module
from app.agent.claim import build_submission_pack, review_claim, submission_blockers

PDF = b"%PDF-1.4 synthetic test file"
POLICY = {
    "doc_id": "p", "status": "confirmed", "corrected_fields": [], "insurer": "Suraksha General (MOCK)",
    "policy_number": "P-1", "policy_type": "individual", "members": ["Ravi Kumar"], "sum_insured": 300000,
    "period_start": "2026-04-01", "period_end": "2027-03-31", "tpa": None,
}
ROLE = {"role": "caregiver", "patient_name": "Ravi Kumar", "relation": "son"}
# The caregiver is the policyholder here, so no proof upload is needed (DEV-025).
AUTHORITY = {"representative_name": "Arjun Kumar", "basis": "policyholder", "proof_doc_id": None,
             "scope": ["file_grievance", "receive_updates", "share_records", "submit_claim"], "expires_on": None,
             "status": "active", "recorded_at": "2026-10-01T10:00:00+05:30", "withdrawn_at": None}


def doc(id_: str, doc_type: str, facts: dict | None = None, status: str = "parsed") -> dict:
    """Parsed document record with the given facts."""
    return {"id": id_, "filename": f"{id_}.pdf", "mime_type": "application/pdf", "path": "",
            "status": status, "doc_type": doc_type, "error": None, "facts": facts}


SUMMARY = doc("ds", "discharge_summary", {"patient_name": "Ravi Kumar", "hospital_name": "Sunrise (MOCK)",
                                          "admission_date": "2026-10-01", "discharge_date": "2026-10-04"})
BILL = doc("bill", "hospital_bill", {"patient_name": "RAVI KUMAR", "admission_date": "2026-10-01",
                                     "discharge_date": "2026-10-04", "total_amount": 50000,
                                     "line_items": [{"head": "Room", "amount": 20000}, {"head": "Surgery", "amount": 30000}]})


def base_state(*docs: dict, **extra) -> dict:
    """Onboarded reimbursement claim with the given documents."""
    return {"policies": [POLICY], "user_role": ROLE, "authority": AUTHORITY, "onboarding": {"complete": True, "missing": []},
            "claim_info": {"claim_type": "reimbursement"}, "documents": list(docs), **extra}


def codes(state: dict) -> list[str]:
    """Issue codes from a fresh review."""
    return [i["code"] for i in review_claim(state)["claim"]["issues"]]


def test_checklist_and_clean_claim():
    """A consistent claim has no issues and only recommended documents missing."""
    claim = review_claim(base_state(SUMMARY, BILL))["claim"]
    assert claim["issues"] == [] and claim["stage"] == "preparing"
    assert claim["checklist"]["missing_required"] == []
    assert submission_blockers(base_state(SUMMARY, BILL)) == []
    assert "missing discharge summary" in submission_blockers(base_state(BILL))


def test_cross_document_checks():
    """Wrong name and disagreeing dates block; bad bill arithmetic and out-of-period dates warn."""
    wrong_name = doc("ds", "discharge_summary", {**SUMMARY["facts"], "patient_name": "Sita Devi"})
    assert "name_mismatch" in codes(base_state(wrong_name, BILL))
    other_date = doc("ds", "discharge_summary", {**SUMMARY["facts"], "discharge_date": "2026-10-05"})
    assert "date_mismatch" in codes(base_state(other_date, BILL))
    bad_total = doc("bill", "hospital_bill", {**BILL["facts"], "total_amount": 55000})
    assert "bill_total_mismatch" in codes(base_state(SUMMARY, bad_total))
    early = doc("ds", "discharge_summary", {**SUMMARY["facts"], "admission_date": "2026-03-01"})
    assert "outside_policy_period" in codes(base_state(early))
    assert submission_blockers(base_state(wrong_name, BILL))[0].startswith("ds.pdf names the patient")


def test_decision_and_query_reading():
    """Decision lines show deductions and missing clauses; a renamed request is flagged as already provided."""
    decision = doc("dec", "insurer_letter", {"letter_kind": "decision", "outcome": "partially_approved",
        "claimed_amount": 50000, "approved_amount": 42000, "line_decisions": [
            {"head": "Room", "claimed": 20000, "approved": 15000, "reason": "room rent limit", "clause": "4.2"},
            {"head": "Surgery", "claimed": 30000, "approved": 27000, "reason": "non-payable items", "clause": None}]})
    claim = review_claim(base_state(SUMMARY, BILL, decision, claim_info={"submitted_on": "2026-10-10"}))["claim"]
    assert claim["stage"] == "decided"
    assert claim["decision"]["difference"] == 8000
    assert [l["deducted"] for l in claim["decision"]["lines"]] == [5000, 3000]
    assert claim["decision"]["missing_clause"] == ["Surgery"]

    query = doc("q", "insurer_letter", {"letter_kind": "query", "requested_documents": [
        {"label": "Discharge card", "doc_type": "discharge_summary"}, {"label": "Pharmacy bills", "doc_type": "pharmacy_bill"}]})
    claim = review_claim(base_state(SUMMARY, BILL, query))["claim"]
    assert claim["stage"] == "query_raised"
    assert [r["already_provided"] for r in claim["query"]["requested"]] == ["ds.pdf", None]
    assert "repeated_request" in [i["code"] for i in claim["issues"]]


def test_approval_invalidated_when_documents_change():
    """An approval holds for the exact pack; adding a document invalidates it."""
    state = base_state(SUMMARY, BILL)
    state["submission_approval"] = {"hash": build_submission_pack(state)["hash"], "approved_at": "x"}
    assert review_claim(state)["claim"]["stage"] == "approved_to_submit"
    state["documents"].append(doc("rx", "prescription", {"patient_name": "Ravi Kumar"}))
    claim = review_claim(state)["claim"]
    assert claim["stage"] == "preparing" and "approval_invalidated" in [i["code"] for i in claim["issues"]]


@pytest.fixture
def client(monkeypatch, tmp_path):
    """API client whose fake model calls prepare_submission once, then replies."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    script = iter([
        AIMessage("", tool_calls=[{"name": "prepare_submission", "id": "c1", "args": {}}]),
        AIMessage("Approved. Submit it through the insurer portal."),
    ])

    class FakeLLM:
        def invoke(self, messages):
            return next(script)

    monkeypatch.setattr(graph_module, "get_llm", lambda tools=None: FakeLLM())
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_prepare_submission_pauses_for_approval(client):
    """prepare_submission shows the pack, waits, and records the approved pack hash on resume."""
    graph = client.app.state.graph
    config = {"configurable": {"thread_id": "s1"}}
    graph.update_state(config, base_state(SUMMARY, BILL))

    paused = client.post("/api/chat", json={"thread_id": "s1", "message": "Please prepare my claim"}).json()
    pack = paused["pending"]["pack"]
    assert paused["pending"]["type"] == "approve_submission"
    assert pack["claimed_amount"] == 50000 and "Rs 50000" in pack["cover_letter"]

    done = client.post("/api/resume", json={"thread_id": "s1", "approved": True}).json()
    assert done["pending"] is None and done["claim"]["stage"] == "approved_to_submit"
    assert graph.get_state(config).values["submission_approval"]["hash"] == pack["hash"]
