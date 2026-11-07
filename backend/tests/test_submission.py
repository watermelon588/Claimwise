"""Next-step buttons, off-plan messages, submission and monitoring (DEV-019 to DEV-022).

A small in-memory connector stands in for the gateway, so no network or model is used.
"""

import hashlib
import hmac
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from app import connector
from app.agent import graph as graph_module, intent, onboarding
from app.agent.actions import next_actions, route_turn
from app.agent.claim import build_submission_pack, review_claim
from app.agent.monitor import claim_documents, reminders, sync_connector
from app.agent.submission import client_reference, record_manual, submit_via_connector
from app.config import get_settings
from tests.test_claim import BILL, PDF, SUMMARY, base_state

SECRET = "test-webhook-secret"


class FakeConnector:
    """In-memory payer behind the connector: idempotent submit, lookup, read, and injectable failures."""

    def __init__(self):
        self.claims: dict[str, dict] = {}
        self.lose_next_response = False
        self.refuse: str | None = None
        self.revoked = False

    def _guard(self):
        """Revoked consent answers 403, like the gateway."""
        if self.revoked:
            raise connector.ConnectorError(403, "CONSENT_REQUIRED")

    def connected_tools(self, case_id):
        """Tools granted on the case."""
        self._guard()
        return ["read_claim", "read_policy"]

    def submit_claim(self, case_id, body, key):
        """Create once per idempotency key; optionally commit and then lose the answer."""
        self._guard()
        if self.refuse:
            raise connector.ConnectorError(422, self.refuse)
        claim = next((c for c in self.claims.values() if c["client_reference"] == key), None)
        if claim is None:
            claim_id = f"CLM-T{len(self.claims) + 1}"
            claim = {"id": claim_id, "client_reference": key, "submitted_at": "2026-11-05T10:00:00+05:30",
                     "claimed_amount": body["claimed_amount"], "queries": [], "decision": None, "payments": []}
            self.claims[claim_id] = claim
        if self.lose_next_response:
            self.lose_next_response = False
            raise connector.ConnectorError(502, "PROVIDER_SUBMIT_UNCONFIRMED")
        return claim

    def find_claims(self, case_id, reference):
        """Claims with this client reference."""
        self._guard()
        return [c for c in self.claims.values() if c["client_reference"] == reference]

    def read_claim(self, case_id, claim_id):
        """Full claim snapshot."""
        self._guard()
        return self.claims[claim_id]


@pytest.fixture
def payer(monkeypatch):
    """Patch the connector client with a fresh fake payer."""
    fake = FakeConnector()
    for name in ("connected_tools", "submit_claim", "find_claims", "read_claim"):
        monkeypatch.setattr(connector, name, getattr(fake, name))
    return fake


def approved_state(**extra) -> dict:
    """Ready claim whose current pack the user approved, with an active connection."""
    state = base_state(SUMMARY, BILL, connection={"case_id": "case-abc", "linked_at": "x", "status": "active"}, **extra)
    state["submission_approval"] = {"hash": build_submission_pack(state)["hash"], "approved_at": "2026-11-05"}
    return state


def with_review(state: dict) -> dict:
    """State plus its C1 review, as the API sees it."""
    return {**state, **review_claim(state)}


def ids(state: dict) -> list[str]:
    """Button ids for a state."""
    return [a["id"] for a in next_actions(with_review(state))]


def test_buttons_follow_the_stage():
    """Preparing offers the pack; approved offers routes; submitted offers letter and nothing-yet."""
    assert ids(base_state(SUMMARY, BILL)) == ["prepare_pack", "other"]
    approved = approved_state()
    assert ids(approved)[:2] == ["submit_connector", "download_pdf"]
    assert ids({**approved, "connection": None})[0] == "download_pdf"  # not connected: manual route only
    submitted = {**approved, "claim_info": {**approved["claim_info"], "submitted_on": "2026-11-05"},
                 "submission": {"route": "connector", "status": "submitted", "claim_id": "CLM-1"}}
    assert ids(submitted) == ["check_updates", "upload_letter", "nothing_yet", "other"]
    assert next_actions({"onboarding": {"complete": False}}) == []


def test_route_turn_sends_each_input_to_the_right_node():
    """Buttons to X1, typed text to I1, uploads and tool results to A1, finished turns to END."""
    assert route_turn({"requested_action": {"id": "nothing_yet"}}) == "run_action"
    assert route_turn({"messages": [HumanMessage("hello")]}) == "classify_intent"
    assert route_turn({"messages": [HumanMessage("I uploaded a file: a.pdf", name="upload")]}) == "agent"
    assert route_turn({"messages": [AIMessage("done")]}) == END
    assert route_turn({}) == END


def test_submit_reconciles_a_lost_response_without_a_duplicate(payer):
    """The payer commits but the answer is lost: the lookup adopts the same claim; a retry creates nothing."""
    state = approved_state()
    payer.lose_next_response = True
    update, text = submit_via_connector(state, "thread-1")
    assert update["submission"]["status"] == "submitted"
    assert update["submission"]["claim_id"] == "CLM-T1" and "CLM-T1" in text
    assert update["claim_info"]["claim_number"] == "CLM-T1"
    again, _ = submit_via_connector({**state, **update}, "thread-1")
    assert again == {} and len(payer.claims) == 1
    ref = client_reference("thread-1", state["submission_approval"]["hash"])
    assert payer.claims["CLM-T1"]["client_reference"] == ref and "thread-1" not in ref


def test_submit_refusal_expiry_and_missing_approval(payer):
    """A payer refusal is recorded; revoked consent expires the connection; no approval sends nothing."""
    payer.refuse = "MEMBER_NOT_COVERED"
    update, _ = submit_via_connector(approved_state(), "t")
    assert update["submission"]["status"] == "refused" and update["submission"]["error"] == "MEMBER_NOT_COVERED"
    payer.refuse, payer.revoked = None, True
    update, _ = submit_via_connector(approved_state(), "t")
    assert update["connection"]["status"] == "expired" and update["notifications"][0]["kind"] == "warning"
    assert submit_via_connector(base_state(SUMMARY, BILL), "t")[0] == {}
    assert payer.claims == {}


def test_manual_submission_date_is_validated():
    """A future or malformed date changes nothing; a real date records the manual route."""
    state = approved_state()
    today = date(2026, 11, 5)
    assert record_manual(state, {"submitted_on": "2026-11-09"}, today)[0] == {}
    assert record_manual(state, {"submitted_on": "yesterday"}, today)[0] == {}
    update, text = record_manual(state, {"submitted_on": "2026-11-03", "claim_number": "AB12"}, today)
    assert update["submission"]["route"] == "manual" and update["claim_info"]["submitted_on"] == "2026-11-03"
    assert "2026-11-18" in text  # settlement due 15 days later


def test_sync_turns_payer_records_into_letters_once(payer):
    """M1 reads a query, a decision and a payment; a second sync adds no duplicate notices."""
    state = approved_state()
    update, _ = submit_via_connector(state, "t")
    state = {**state, **update, "claim_info": {**state["claim_info"], **update["claim_info"]}}
    claim = payer.claims["CLM-T1"]
    claim["queries"].append({"id": "Q1", "raised_at": "2026-11-06T09:00:00", "due_at": "2026-11-20T00:00:00",
                             "status": "open", "items": [{"code": "pharmacy_bills", "label": "Pharmacy bills"}]})
    first = sync_connector(state, today=date(2026, 11, 6))
    letter = first["documents"][0]
    assert letter["source"] == "connector" and letter["facts"]["letter_kind"] == "query"
    assert letter["facts"]["requested_documents"][0]["doc_type"] == "pharmacy_bill"
    assert any("Pharmacy bills" in n["text"] for n in first["notifications"])
    merged = {**state, "documents": state["documents"] + first["documents"],
              "notifications": first["notifications"], "submission": first["submission"]}
    assert "notifications" not in sync_connector(merged, today=date(2026, 11, 6))

    claim["decision"] = {"decided_at": "2026-11-10T10:00:00", "outcome": "partially_approved",
                         "approved_amount": 4_000_000, "line_decisions": [], "rejection_reason": None, "policy_clause": None}
    claim["payments"].append({"utr": "UTR123", "amount": 4_000_000, "paid_at": "2026-11-12T10:00:00"})
    later = sync_connector(merged, today=date(2026, 11, 12))
    kinds = {d["facts"]["letter_kind"]: d["facts"] for d in later["documents"]}
    assert kinds["decision"]["approved_amount"] == 40000 and kinds["settlement"]["utr"] == "UTR123"


def test_reminders_fire_once_by_date():
    """Overdue after 15 days without a decision; a query due soon; each reminder id appears once."""
    state = base_state(SUMMARY, BILL, claim_info={"claim_type": "reimbursement", "submitted_on": "2026-10-01"},
                       submission={"route": "manual", "status": "submitted"})
    notes = reminders(state, date(2026, 10, 20))
    assert [n["kind"] for n in notes] == ["warning"] and "19 days" in notes[0]["text"]
    assert reminders({**state, "notifications": notes}, date(2026, 10, 21)) == []
    query = {"id": "q", "filename": "q", "mime_type": "application/json", "path": "", "status": "parsed",
             "doc_type": "insurer_letter", "error": None,
             "facts": {"letter_kind": "query", "due_on": "2026-10-22", "query_status": "open", "requested_documents": []}}
    soon = reminders({**state, "documents": [*state["documents"], query], "notifications": notes}, date(2026, 10, 20))
    # The open query stops the settlement clock, so the earlier overdue warning is resolved, not left active.
    assert [n["id"] for n in soon] == ["rem-q-soon", "rem-overdue-2026-10-01"]
    assert soon[1]["resolved"] and soon[1]["read"]
    # An open query stops the settlement clock: no overdue warning, only the query reminder.
    assert [n["id"] for n in reminders({**state, "documents": [*state["documents"], query]}, date(2026, 10, 20))] == ["rem-q-soon"]
    late = reminders({**state, "documents": [*state["documents"], query]}, date(2026, 10, 25))
    assert late[0]["id"] == "rem-q-late" and "3 days ago" in late[0]["text"]
    # Once answered, the 15 days restart from the answer date.
    answered = {**query, "facts": {**query["facts"], "query_status": "answered", "answered_on": "2026-10-15"}}
    with_answer = {**state, "documents": [*state["documents"], answered]}
    assert reminders(with_answer, date(2026, 10, 25)) == []
    assert "17 days" in reminders(with_answer, date(2026, 11, 1))[0]["text"]
    assert review_claim(with_answer)["claim"]["stage"] == "submitted"


def test_claim_documents_shape_matches_letters():
    """Connector snapshots become insurer letters in rupees with stable ids."""
    snap = {"id": "CLM-9", "claimed_amount": 5_000_000, "queries": [], "payments": [],
            "decision": {"decided_at": "2026-11-01T00:00:00", "outcome": "rejected", "approved_amount": 0,
                         "rejection_reason": "Waiting period", "policy_clause": "4.2"}}
    [doc] = claim_documents(snap)
    assert doc["id"] == "tpa-decision-CLM9-20261101T000000"
    assert doc["facts"]["claimed_amount"] == 50000 and doc["facts"]["clause"] == "4.2"


@pytest.fixture
def api(monkeypatch, tmp_path, payer):
    """API client with an in-memory graph, fake model and extraction, connectors and webhook enabled."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTOR_URL", "http://connector.test")
    monkeypatch.setenv("MOCK_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()

    class FakeModel:
        """Plain reply for model turns."""

        def invoke(self, _messages):
            return AIMessage("Noted.")

    def extract(document):
        """Fixed facts by file name."""
        source = SUMMARY if document["filename"] == "summary.pdf" else BILL
        field = onboarding.HospitalFields(**source["facts"])
        return onboarding.DocumentExtraction(doc_type=source["doc_type"], hospital=field)

    monkeypatch.setattr(graph_module, "get_llm", lambda _tools: FakeModel())
    monkeypatch.setattr(onboarding, "extract_document", extract)
    from app.main import app

    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def signed(body: dict) -> tuple[bytes, dict]:
    """Raw webhook body and its signature header."""
    raw = json.dumps(body).encode()
    return raw, {"X-Mock-Signature": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(),
                 "Content-Type": "application/json"}


def test_api_journey_with_buttons_connector_and_webhook(api, payer, monkeypatch):
    """Prepare and approve, connect, submit, then a signed webhook brings the decision in."""
    thread = "journey-024"
    api.app.state.graph.update_state({"configurable": {"thread_id": thread}}, base_state())
    for name in ("summary.pdf", "bill.pdf"):
        r = api.post("/api/documents", data={"thread_id": thread}, files={"file": (name, PDF + name.encode(), "application/pdf")})
        assert r.status_code == 200, r.text
    assert [a["id"] for a in r.json()["actions"]] == ["prepare_pack", "other"]

    # A button that is not offered now is refused; a browser-only one is not run on the server.
    assert api.post("/api/action", json={"thread_id": thread, "action": "submit_connector"}).status_code == 409
    assert api.post("/api/action", json={"thread_id": thread, "action": "other"}).status_code == 422

    assert api.post("/api/action", json={"thread_id": thread, "action": "prepare_pack"}).json()["pending"]
    approved = api.post("/api/resume", json={"thread_id": thread, "approved": True}).json()
    assert approved["claim"]["stage"] == "approved_to_submit"
    assert [a["id"] for a in approved["actions"]][0] == "download_pdf"

    # Off-topic text gets the fixed reply and changes nothing.
    monkeypatch.setattr(intent, "classify", lambda text: "off_topic")
    off = api.post("/api/chat", json={"thread_id": thread, "message": "write me a poem"}).json()
    assert "download PDF" in off["reply"] and off["claim"]["stage"] == "approved_to_submit"

    linked = api.post("/api/connection", json={"thread_id": thread, "code": "case-abc-123"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["connection"]["status"] == "active" and "case_id" not in linked.json()["connection"]
    sent = api.post("/api/action", json={"thread_id": thread, "action": "submit_connector"}).json()
    assert sent["submission"]["status"] == "submitted" and "client_reference" not in sent["submission"]
    assert sent["claim"]["stage"] == "submitted" and len(payer.claims) == 1

    # Bad signature is refused; a signed event for an unknown claim is ignored.
    raw, headers = signed({"event_type": "claim.decided", "resource": {"type": "claim", "id": "CLM-T1"}})
    assert api.post("/api/webhooks/mock", content=raw, headers={**headers, "X-Mock-Signature": "sha256=bad"}).status_code == 401
    other, other_headers = signed({"event_type": "claim.decided", "resource": {"type": "claim", "id": "CLM-NOPE"}})
    assert api.post("/api/webhooks/mock", content=other, headers=other_headers).json() == {"status": "ignored"}

    payer.claims["CLM-T1"]["decision"] = {"decided_at": "2026-11-06T10:00:00", "outcome": "approved",
                                          "approved_amount": 5_000_000, "line_decisions": []}
    assert api.post("/api/webhooks/mock", content=raw, headers=headers).json() == {"status": "refreshed"}
    state = api.get(f"/api/thread/{thread}").json()
    assert state["claim"]["stage"] == "decided"
    assert any("approved" in n["text"] for n in state["notifications"])
    assert all(not n["read"] for n in state["notifications"])
    read = api.post("/api/notifications/read", json={"thread_id": thread}).json()
    assert read["notifications"] and all(n["read"] for n in read["notifications"])


def test_api_manual_route_and_nothing_yet(api):
    """Without a connection: record the manual submission, then 'Nothing yet' gives the due date."""
    thread = "manual-024"
    api.app.state.graph.update_state({"configurable": {"thread_id": thread}}, base_state())
    for name in ("summary.pdf", "bill.pdf"):
        api.post("/api/documents", data={"thread_id": thread}, files={"file": (name, PDF + name.encode(), "application/pdf")})
    api.post("/api/action", json={"thread_id": thread, "action": "prepare_pack"})
    api.post("/api/resume", json={"thread_id": thread, "approved": True})
    today = date.today().isoformat()
    done = api.post("/api/action", json={"thread_id": thread, "action": "submitted_manually",
                                         "data": {"submitted_on": today}}).json()
    assert done["claim"]["stage"] == "submitted" and done["submission"]["route"] == "manual"
    wait = api.post("/api/action", json={"thread_id": thread, "action": "nothing_yet"}).json()
    assert wait["reply"] and [a["id"] for a in wait["actions"]] == ["upload_letter", "nothing_yet", "other"]
