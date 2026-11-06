"""Follow-up gaps closed in session 037: top-up after a revised decision, answering an insurer query,
policy corrections checked at the API, the thread list limited to the caller's ids, and the provider name.

No model or network: the connector is patched.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import connector
from app.agent import actions
from app.agent.actions import HANDLERS, next_actions
from app.agent.claim import review_claim
from app.agent.onboarding import correction_error
from app.agent.payment import verify_payment
from app.agent.submission import provider_name
from app.config import get_settings
from tests.test_claim import BILL, POLICY, SUMMARY, base_state, doc

CONN = {"case_id": "case-abc", "linked_at": "x", "status": "active"}
SUBMITTED = {"route": "connector", "status": "submitted", "claim_id": "CLM-1", "pack_hash": "h", "client_reference": "r"}


def reviewed(state: dict) -> dict:
    """State with its C1 review and, once decided, the P1 payment check (as the graph runs them)."""
    state = {**state, **review_claim(state)}
    return {**state, **verify_payment(state)} if state["claim"]["decision"] else state


def letter(id_: str, **facts) -> dict:
    """An insurer letter record."""
    return doc(id_, "insurer_letter", {"claim_number": "CLM-1", **facts})


def test_top_up_due_after_a_revised_decision():
    """Paid in full for the first decision; the revised decision raises the amount: the rest is a top-up, not a mismatch."""
    paid = letter("pay", letter_kind="settlement", paid_amount=33020, utr="UTR1", paid_on="2026-10-20", letter_date="2026-10-20")
    revised = letter("rev", letter_kind="decision", outcome="partially_approved", claimed_amount=65000,
                     approved_amount=64000, letter_date="2026-11-05")
    claim = reviewed(base_state(SUMMARY, BILL, paid, revised))["claim"]
    assert claim["payment"]["status"] == "top_up_due" and claim["payment"]["top_up"] == 30980
    assert claim["stage"] == "payment_reported"
    codes = {i["code"] for i in claim["issues"]}
    assert "top_up_due" in codes and "short_payment" not in codes
    # A payment after the decision is checked normally: paying less than approved is a short payment.
    late = letter("pay2", letter_kind="settlement", paid_amount=33020, utr="UTR2", paid_on="2026-11-06", letter_date="2026-11-06")
    claim = reviewed(base_state(SUMMARY, BILL, revised, late))["claim"]
    assert claim["payment"]["status"] == "mismatch" and "short_payment" in {i["code"] for i in claim["issues"]}


def query_state(*later: dict) -> dict:
    """Connector claim with an open query for the discharge summary (renamed) and lab reports."""
    q = {**letter("tpa-query-1", letter_kind="query", letter_date="2026-11-01", query_status="open", due_on="2026-11-10",
                  requested_documents=[{"label": "Discharge Card", "doc_type": "discharge_summary"},
                                       {"label": "Lab reports", "doc_type": "investigation_report"}]),
         "source": "connector", "uploaded_at": "2026-11-01T10:00:00+05:30"}
    early = [{**d, "uploaded_at": "2026-10-20T10:00:00+05:30"} for d in (SUMMARY, BILL)]
    return base_state(*early, q, *later, connection=CONN, submission=SUBMITTED,
                      claim_info={"claim_type": "reimbursement", "submitted_on": "2026-10-21", "claim_number": "CLM-1"})


def test_query_reply_goes_through_the_connector_only_after_approval(monkeypatch):
    """Send is offered once every item is on file; a later upload answers the query, it is not 'already sent'."""
    state = reviewed(query_state())
    ids = [a["id"] for a in next_actions(state)]
    assert "draft_already_sent" in ids and "send_query_reply" not in ids
    lab = {**doc("lab", "investigation_report", {"patient_name": "Ravi Kumar"}), "uploaded_at": "2026-11-02T09:00:00+05:30"}
    state = reviewed(query_state(lab))
    repeated = [i for i in state["claim"]["issues"] if i["code"] == "repeated_request"]
    assert len(repeated) == 1 and "Discharge Card" in repeated[0]["message"]  # the lab report is an answer, not a repeat
    assert "send_query_reply" in [a["id"] for a in next_actions(state)]

    sent = []
    monkeypatch.setattr(connector, "answer_query", lambda case, claim, docs: sent.append((case, claim, docs)) or {})
    monkeypatch.setattr(actions, "interrupt", lambda card: {"approved": False})
    update, text = HANDLERS["send_query_reply"](state, {}, "t")
    assert update == {} and not sent and "Nothing was sent" in text
    cards = []
    monkeypatch.setattr(actions, "interrupt", lambda card: cards.append(card) or {"approved": True})
    update, text = HANDLERS["send_query_reply"](state, {}, "t")
    assert cards[0]["kind"] == "query_reply" and "lab.pdf" in cards[0]["letter"]
    assert [d["id"] for d in sent[0][2]] == ["ds", "lab"] and sent[0][:2] == ("case-abc", "CLM-1")
    after = reviewed({**state, "documents": [d if d["id"] != "tpa-query-1" else update["documents"][0] for d in state["documents"]]})
    assert after["claim"]["stage"] == "submitted"


def test_query_reply_refused_or_expired(monkeypatch):
    """An insurer with no open query, or a revoked connection, is reported without changing the claim wrongly."""
    lab = {**doc("lab", "investigation_report", {}), "uploaded_at": "2026-11-02T09:00:00+05:30"}
    state = reviewed(query_state(lab))
    monkeypatch.setattr(actions, "interrupt", lambda card: {"approved": True})

    def refuse(code, status):
        def call(*_):
            raise connector.ConnectorError(status, code)
        return call

    monkeypatch.setattr(connector, "answer_query", refuse("QUERY_NOT_OPEN", 409))
    assert HANDLERS["send_query_reply"](state, {}, "t") == ({}, actions.QUERY_NOT_OPEN_REPLY)
    monkeypatch.setattr(connector, "answer_query", refuse("PROVIDER_NOT_CONNECTED", 403))
    update, _ = HANDLERS["send_query_reply"](state, {}, "t")
    assert update["connection"]["status"] == "expired"


def test_deduction_without_a_clause_is_flagged():
    """V-14: a deduction that cites no policy clause raises clause_not_cited; a cited one does not."""
    lines = [{"head": "Pharmacy", "claimed": 10000, "approved": 6000, "reason": "Non-payable items"},
             {"head": "Room rent", "claimed": 12000, "approved": 9000, "reason": "Above limit", "clause": "Section 3.2"}]
    dec = letter("dec", letter_kind="decision", outcome="partially_approved", claimed_amount=65000,
                 approved_amount=58000, letter_date="2026-11-05", line_decisions=lines)
    claim = reviewed(base_state(SUMMARY, BILL, dec))["claim"]
    flagged = [i for i in claim["issues"] if i["code"] == "clause_not_cited"]
    assert claim["decision"]["missing_clause"] == ["Pharmacy"] and len(flagged) == 1 and "Pharmacy" in flagged[0]["message"]
    cited = letter("dec", letter_kind="decision", outcome="partially_approved", claimed_amount=65000,
                   approved_amount=58000, letter_date="2026-11-05", line_decisions=[lines[1]])
    assert "clause_not_cited" not in {i["code"] for i in reviewed(base_state(SUMMARY, BILL, cited))["claim"]["issues"]}


def test_pack_is_never_re_approved_after_submission(monkeypatch):
    """Live J5: the model called prepare_submission after a query upload; a submitted claim must refuse it."""
    from app.agent.tools import request_pack_approval

    monkeypatch.setattr("app.agent.tools.interrupt", lambda card: pytest.fail("no approval card after submission"))
    outcome, reasons = request_pack_approval(query_state())
    assert outcome == "blocked" and "already submitted" in reasons[0]


def test_check_submission_points_to_retry_when_the_payer_never_got_it(monkeypatch):
    """After an outage: 'not at the payer' leads to the safe retry; 'payer unreachable' still says wait."""
    state = base_state(SUMMARY, BILL, connection=CONN, claim_info={"claim_type": "reimbursement"}, submission={
        "route": "connector", "status": "unconfirmed", "claim_id": None, "client_reference": "r", "pack_hash": "h"})
    monkeypatch.setattr(connector, "find_claims", lambda case, ref: [])
    update, text = HANDLERS["check_submission"](state, {}, "t")
    assert update["submission"]["error"] == "NOT_AT_PAYER" and "Try submitting again" in text

    def down(*_):
        raise connector.ConnectorError(0, "GATEWAY_UNREACHABLE")

    monkeypatch.setattr(connector, "find_claims", down)
    assert HANDLERS["check_submission"](state, {}, "t") == ({}, actions.UNCONFIRMED_REPLY)


def test_manual_query_answer_date_is_validated():
    """An uploaded query letter offers 'I sent what they asked for'; the date restarts the 15 days."""
    q = {**letter("q", letter_kind="query", letter_date="2026-11-01",
                  requested_documents=[{"label": "Aadhaar", "doc_type": "id_proof"}]), "uploaded_at": "2026-11-01T10:00:00+05:30"}
    state = reviewed(base_state(SUMMARY, BILL, q, submission={**SUBMITTED, "route": "manual"},
                                claim_info={"claim_type": "reimbursement", "submitted_on": "2026-10-21"}))
    assert "query_answered" in [a["id"] for a in next_actions(state)]
    for bad in ((date.today() + timedelta(days=1)).isoformat(), "2026-10-30", "soon"):
        assert HANDLERS["query_answered"](state, {"date": bad}, "t")[0] == {}
    update, text = HANDLERS["query_answered"](state, {"date": "2026-11-03"}, "t")
    assert update["documents"][0]["facts"]["answered_on"] == "2026-11-03" and "2026-11-18" in text
    assert review_claim({**state, "documents": [SUMMARY, BILL, update["documents"][0]]})["claim"]["stage"] == "submitted"


def test_policy_corrections_are_checked_before_resuming():
    """A wrong type is refused with the field name; unknown fields are ignored; good values pass."""
    assert "sum_insured" in correction_error(POLICY, {"sum_insured": "five lakh"})
    assert correction_error(POLICY, {"sum_insured": 500000, "not_a_field": "x"}) is None


@pytest.fixture
def api(monkeypatch, tmp_path):
    """API with in-memory checkpoints."""
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_thread_list_returns_only_the_callers_threads(api):
    """No ids, no claims: the server never lists every thread in the database."""
    graph = api.app.state.graph
    for tid in ("mine-1", "someone-else"):
        graph.update_state({"configurable": {"thread_id": tid}}, {"claim_info": {"claim_type": "cashless"}}, as_node="reply_off_topic")
    assert api.get("/api/threads").json() == []
    listed = api.get("/api/threads", params={"ids": "mine-1,../etc,mine-1,missing"}).json()
    assert [t["thread_id"] for t in listed] == ["mine-1"]


def test_provider_name_follows_the_policy():
    """Replies name the policy's TPA, else its insurer."""
    assert provider_name(base_state()) == POLICY["insurer"]
    assert provider_name(base_state(policies=[{**POLICY, "tpa": "Medivista TPA"}])) == "Medivista TPA"


def test_claim_type_is_recorded_without_the_model(api):
    """The buttons record the claim type directly; a submitted claim cannot change type."""
    graph = api.app.state.graph
    graph.update_state({"configurable": {"thread_id": "ct-1"}}, {"user_role": {"role": "self", "patient_name": "A", "relation": "self"}},
                       as_node="reply_off_topic")
    r = api.post("/api/claim-type", json={"thread_id": "ct-1", "claim_type": "reimbursement"})
    assert r.status_code == 200 and r.json()["answers"]["claimType"] == "reimbursement"
    assert r.json()["audit"][0]["action"] == "set_claim_type"
    assert api.post("/api/claim-type", json={"thread_id": "ct-1", "claim_type": "other"}).status_code == 422
    graph.update_state({"configurable": {"thread_id": "ct-1"}}, {"claim_info": {"submitted_on": "2026-11-01"}}, as_node="reply_off_topic")
    assert api.post("/api/claim-type", json={"thread_id": "ct-1", "claim_type": "cashless"}).status_code == 409
