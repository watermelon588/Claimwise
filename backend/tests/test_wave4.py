"""Wave 4 journeys (DEV-023 to DEV-026) through the real API, with fake extraction, model and payer.

Each test is the end-to-end check named in the build queue:
- versions: the same bill twice, then a corrected bill; versions and the approval reset are right;
- household: two policies, the primary partly pays, a balance claim is prepared for the second;
- authority: a caregiver with proof proceeds; consent withdrawn mid-claim blocks submission;
- disputes: partial approval, grievance, 14 days, Ombudsman draft, a revised decision reopens the check.
All data is synthetic.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent import graph as graph_module, onboarding
from app.agent.claim import build_submission_pack, read_query, review_claim
from app.agent.submission import submission_payload, submit_via_connector
from app.config import get_settings
from tests.test_claim import AUTHORITY, BILL, PDF, POLICY, SUMMARY, base_state, doc
from tests.test_submission import payer  # noqa: F401  (fixture)

TODAY = date.today()
CONSENT = {"grantor_name": "Ravi Kumar", "representative_name": "Arjun Kumar",
           "issued_on": "2026-10-01", "valid_until": (TODAY + timedelta(days=200)).isoformat()}
# File name -> (doc_type, facts) returned by the fake document reader.
FACTS = {
    "summary.pdf": (SUMMARY["doc_type"], SUMMARY["facts"]),
    "bill.pdf": (BILL["doc_type"], BILL["facts"]),
    "bill-corrected.pdf": (BILL["doc_type"], {**BILL["facts"], "total_amount": 52000}),
    "consent.pdf": ("authority_proof", CONSENT),
}


def days_ago(n: int) -> str:
    """ISO date n days before today."""
    return (TODAY - timedelta(days=n)).isoformat()


def decision(id_: str, approved: int, when: str) -> dict:
    """A parsed decision letter: room fully approved, surgery cut, no clause on the cut."""
    return doc(id_, "insurer_letter", {
        "letter_kind": "decision", "letter_date": when, "claim_number": "CLM-W4", "outcome": "partially_approved",
        "claimed_amount": 50000, "approved_amount": approved, "requested_documents": [], "reason": None,
        "clause": None, "line_decisions": [
            {"head": "Room", "claimed": 20000, "approved": 20000, "reason": None, "clause": None},
            {"head": "Surgery", "claimed": 30000, "approved": approved - 20000, "reason": "Reasonable charges",
             "clause": None},
        ]})


@pytest.fixture
def api(monkeypatch, tmp_path, payer):  # noqa: F811
    """API client: in-memory graph, fake model, extraction by file name, connector enabled."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTOR_URL", "http://connector.test")
    get_settings.cache_clear()

    class FakeModel:
        def invoke(self, _messages):
            return AIMessage("Noted.")

    def extract(document):
        """Facts by file name, in the model's output shape."""
        doc_type, facts = FACTS[document["filename"]]
        if doc_type == "authority_proof":
            return onboarding.DocumentExtraction(doc_type=doc_type, authority=onboarding.AuthorityFields(**facts))
        return onboarding.DocumentExtraction(doc_type=doc_type, hospital=onboarding.HospitalFields(**facts))

    monkeypatch.setattr(graph_module, "get_llm", lambda _tools=None: FakeModel())
    monkeypatch.setattr(onboarding, "extract_document", extract)
    from app.main import app

    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def upload(api, thread: str, name: str, content: bytes = PDF):
    """Upload one file through the real route."""
    return api.post("/api/documents", data={"thread_id": thread}, files={"file": (name, content, "application/pdf")})


def press(api, thread: str, action: str, data: dict | None = None):
    """Press one button."""
    return api.post("/api/action", json={"thread_id": thread, "action": action, "data": data or {}})


def approve(api, thread: str) -> dict:
    """Approve the waiting card."""
    return api.post("/api/resume", json={"thread_id": thread, "approved": True}).json()


def put(api, thread: str, update: dict) -> dict:
    """Write state while the thread is at rest (like an insurer letter arriving), then reopen the claim."""
    config = {"configurable": {"thread_id": thread}}
    api.app.state.graph.update_state(config, update, as_node="reply_off_topic")
    return api.get(f"/api/thread/{thread}").json()


def state_of(api, thread: str) -> dict:
    """Saved graph state."""
    return api.app.state.graph.get_state({"configurable": {"thread_id": thread}}).values


def test_versions_duplicate_then_corrected_bill(api):
    """DEV-023: the same bill twice adds nothing; a corrected bill asks replace or keep; replace resets approval."""
    thread = "w4-versions"
    put(api, thread, base_state())
    assert upload(api, thread, "summary.pdf", PDF + b"s").status_code == 200
    assert upload(api, thread, "bill.pdf", PDF + b"b").status_code == 200
    press(api, thread, "prepare_pack")
    assert approve(api, thread)["claim"]["stage"] == "approved_to_submit"

    again = upload(api, thread, "bill.pdf", PDF + b"b")
    assert again.status_code == 409 and "already in your claim as bill.pdf" in again.json()["detail"]
    assert len(state_of(api, thread)["documents"]) == 2

    corrected = upload(api, thread, "bill-corrected.pdf", PDF + b"c").json()
    assert [a["id"] for a in corrected["actions"]][:2] == ["replace_version", "keep_version"]
    assert "version_choice" in {i["code"] for i in corrected["claim"]["issues"]}
    new_id = corrected["actions"][0]["data"]["doc_id"]
    assert press(api, thread, "replace_version", {"doc_id": "someone-else"}).status_code == 409

    done = press(api, thread, "replace_version", {"doc_id": new_id}).json()
    assert "replaced bill.pdf (now version 2)" in done["reply"] and "review the pack again" in done["reply"]
    docs = {d["filename"]: d for d in done["documents"]}
    assert docs["bill.pdf"]["status"] == "superseded" and docs["bill-corrected.pdf"]["version"] == 2
    assert state_of(api, thread)["submission_approval"] is None
    assert done["claim"]["stage"] == "preparing" and [a["id"] for a in done["actions"]] == ["prepare_pack", "other"]
    pack = press(api, thread, "prepare_pack").json()["pending"]["pack"]
    assert pack["claimed_amount"] == 52000 and "bill.pdf" not in {d["filename"] for d in pack["documents"]}
    assert any(a["action"] == "replace_version" for a in done["audit"])


def test_repeated_request_reply_names_the_earlier_upload():
    """DEV-023: a query asking again for a bill already given gets a ready 'already sent on <date>' reply."""
    bill = {**BILL, "uploaded_at": "2026-10-10T09:00:00+05:30"}
    query = doc("q", "insurer_letter", {"letter_kind": "query", "letter_date": "2026-10-20", "requested_documents": [
        {"label": "Final hospital bill", "doc_type": "hospital_bill"}]})
    state = base_state(SUMMARY, bill, query, claim_info={"claim_type": "reimbursement", "submitted_on": "2026-10-12",
                                                          "claim_number": "CLM-9"})
    state = {**state, **review_claim(state)}
    issue = next(i for i in state["claim"]["issues"] if i["code"] == "repeated_request")
    assert "already sent on 2026-10-10 as bill.pdf" in issue["message"]
    from app.agent.actions import _already_sent, next_actions
    assert "draft_already_sent" in [a["id"] for a in next_actions(state)]
    assert read_query(state)["requested"][0]["provided_on"] == "2026-10-10"
    _, text = _already_sent(state, {}, "t")
    assert "Claim CLM-9" in text and "Final hospital bill: sent on 2026-10-10 as bill.pdf" in text


def test_household_choose_primary_then_balance_on_second(api):
    """DEV-024: two policies; the claimant picks the primary; it partly pays; a balance claim goes to the second."""
    thread = "w4-household"
    group = {**POLICY, "doc_id": "g", "insurer": "Arogya Shield (MOCK)", "policy_number": "G-88",
             "policy_type": "group"}
    first = put(api, thread, base_state(SUMMARY, BILL, policies=[POLICY, group]))
    assert "choose_policy" in {i["code"] for i in first["claim"]["issues"]}
    choices = [a for a in first["actions"] if a["id"] == "choose_policy"]
    assert [c["data"]["doc_id"] for c in choices] == ["p", "g"] and "prepare_pack" not in [a["id"] for a in first["actions"]]

    chosen = press(api, thread, "choose_policy", {"doc_id": "p"}).json()
    assert "policy P-1" in chosen["reply"] and chosen["household"]["chosen"] == "p"
    press(api, thread, "prepare_pack")
    approve(api, thread)
    press(api, thread, "submitted_manually", {"submitted_on": days_ago(20), "claim_number": "CLM-W4"})

    decided = put(api, thread, {"documents": [decision("d1", 30000, days_ago(10))]})
    assert decided["claim"]["stage"] == "decided"
    balance = next(a for a in decided["actions"] if a["id"] == "start_balance_claim")
    assert balance["data"] == {"doc_id": "g"} and "G-88" in balance["label"]

    started = press(api, thread, "start_balance_claim", {"doc_id": "g"}).json()
    assert "Rs 20000" in started["reply"] and started["claim"]["stage"] == "preparing"
    house = started["household"]
    assert house["chosen"] == "g" and house["round"] == 2 and house["balance_of"]["balance"] == 20000
    assert house["history"][0]["policy_number"] == "P-1" and house["history"][0]["approved"] == 30000
    assert {d["id"]: d["status"] for d in started["documents"]}["d1"] == "archived"
    assert started["submission"] is None and started["dispute"] is None

    pack = press(api, thread, "prepare_pack").json()["pending"]["pack"]
    assert pack["policy_number"] == "G-88" and pack["claimed_amount"] == 20000
    assert "d1" in {d["id"] for d in pack["documents"]}  # the first decision letter goes in as evidence
    assert "balance claim" in pack["cover_letter"] and "Rs 30000 of Rs 50000" in pack["cover_letter"]


def test_caregiver_with_proof_then_consent_withdrawn(api, payer):  # noqa: F811
    """DEV-025: authority checked against the proof; withdrawal mid-claim cancels approval and blocks submission."""
    thread = "w4-authority"
    start = {k: v for k, v in base_state().items() if k != "authority"}
    start["connection"] = {"case_id": "case-abc", "linked_at": "x", "status": "active"}
    opened = put(api, thread, start)
    assert opened["onboarding"]["missing"] == ["authority"] and opened["actions"] == []

    proof_id = upload(api, thread, "consent.pdf", PDF + b"p").json()["documents"][0]["id"]
    form = {"thread_id": thread, "representative_name": "Someone Else", "basis": "patient_consent",
            "proof_doc_id": proof_id, "scope": ["submit_claim", "file_grievance"]}
    wrong = api.post("/api/authority", json=form)
    assert wrong.status_code == 422 and "names Arjun Kumar" in wrong.json()["detail"]
    ok = api.post("/api/authority", json={**form, "representative_name": "Arjun Kumar"}).json()
    assert ok["authority"]["status"] == "active" and ok["authority"]["expires_on"] == CONSENT["valid_until"]
    assert ok["onboarding"]["complete"] and ok["audit"][0]["action"] == "record_authority"
    assert ok["audit"][0]["actor"] == "Arjun Kumar (son of Ravi Kumar)"

    upload(api, thread, "summary.pdf", PDF + b"s")
    upload(api, thread, "bill.pdf", PDF + b"b")
    press(api, thread, "prepare_pack")
    ready = approve(api, thread)
    assert [a["id"] for a in ready["actions"]][0] == "submit_connector"

    stopped = api.post("/api/authority/withdraw", json={"thread_id": thread}).json()
    assert stopped["authority"]["status"] == "withdrawn" and stopped["actions"] == []
    assert "withdrawn" in stopped["notifications"][0]["text"]
    assert state_of(api, thread)["submission_approval"] is None
    assert press(api, thread, "submit_connector").status_code == 409
    reply = submit_via_connector(state_of(api, thread), thread)[1]
    assert "was withdrawn" in reply and not payer.claims
    assert api.post("/api/authority/withdraw", json={"thread_id": thread}).status_code == 409

    # The representative's name travels with an online submission, so the payer can check its own records.
    ready_state = base_state(SUMMARY, BILL)
    body, _ = submission_payload(ready_state, build_submission_pack(ready_state), "ref-12345678")
    assert body["acting_user"] == AUTHORITY["representative_name"]


def test_dispute_grievance_ombudsman_and_revised_decision(api):
    """DEV-026: partial approval, grievance approved and sent, 14 days, Ombudsman draft, revised decision reopens."""
    thread = "w4-dispute"
    put(api, thread, base_state(SUMMARY, BILL))
    press(api, thread, "prepare_pack")
    approve(api, thread)
    press(api, thread, "submitted_manually", {"submitted_on": days_ago(60), "claim_number": "CLM-W4"})
    decided = put(api, thread, {"documents": [decision("d1", 30000, days_ago(40))]})
    assert decided["dispute"]["status"] == "open" and decided["dispute"]["disputed_amount"] == 20000
    assert "draft_grievance" in [a["id"] for a in decided["actions"]]

    card = press(api, thread, "draft_grievance").json()["pending"]
    assert card["type"] == "approve_letter" and card["kind"] == "grievance"
    assert "Surgery: claimed Rs 30000, approved Rs 10000, deducted Rs 20000" in card["letter"]
    assert "Clause cited: none cited" in card["letter"] and "Arjun Kumar (son of Ravi Kumar)" in card["letter"]
    letter_ok = approve(api, thread)
    assert letter_ok["dispute"]["status"] == "grievance_approved" and card["letter"] in letter_ok["reply"]
    sent_button = next(a for a in letter_ok["actions"] if a["id"] == "grievance_sent")
    assert sent_button["kind"] == "form"
    assert "not before the decision" in press(api, thread, "grievance_sent", {"date": days_ago(50)}).json()["reply"]

    filed = press(api, thread, "grievance_sent", {"date": days_ago(15), "reference": "GRV-77"}).json()
    assert filed["dispute"]["status"] == "grievance_filed" and filed["dispute"]["grievance_due"] == days_ago(1)
    later = api.get(f"/api/thread/{thread}").json()
    assert any("No reply to your grievance" in n["text"] for n in later["notifications"])
    early = press(api, thread, "draft_ombudsman").json()
    assert "still has until" in early["reply"] and early["pending"] is None

    # The insurer replies without changing anything: the Ombudsman route opens.
    reply = doc("r1", "insurer_letter", {"letter_kind": "grievance_reply", "letter_date": days_ago(5),
                                         "requested_documents": [], "line_decisions": []})
    replied = put(api, thread, {"documents": [reply]})
    assert replied["dispute"]["insurer_reply_on"] == days_ago(5) and replied["dispute"]["ombudsman_eligible"]
    card = press(api, thread, "draft_ombudsman").json()["pending"]
    assert card["kind"] == "ombudsman" and "replied on " + days_ago(5) in card["letter"]
    assert "GRV-77" in card["letter"] and "Amount in dispute: Rs 20000" in card["letter"]
    approve(api, thread)
    lodged = press(api, thread, "ombudsman_sent", {"date": days_ago(1)}).json()
    assert lodged["dispute"]["status"] == "ombudsman_filed"

    # A revised decision reopens only the decision and the payment check.
    revised = put(api, thread, {"documents": [decision("d2", 45000, days_ago(0))]})
    assert revised["dispute"]["status"] == "revised" and revised["claim"]["decision"]["approved"] == 45000
    assert revised["claim"]["payment"]["expected"] == 45000
    assert any("revised decision arrived after your Ombudsman complaint" in n["text"] for n in revised["notifications"])
    assert revised["submission"]["claim_id"] == "CLM-W4"
    assert "draft_grievance" in [a["id"] for a in revised["actions"]]  # Rs 5000 still deducted
    assert {"draft_grievance", "grievance_sent", "ombudsman_sent"} <= {a["action"] for a in revised["audit"]}
