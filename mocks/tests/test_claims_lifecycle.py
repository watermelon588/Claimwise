"""Integration tests covering the end-to-end claim lifecycle and recovery."""

import pytest
from fastapi.testclient import TestClient
from mocks.main import app
from mocks.services.scenarios import reset_database

client = TestClient(app)
API_HEADERS = {"X-Api-Key": "claimwise-demo-key"}


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()


def test_policy_lookup_and_eligibility():
    """Verify policy details and eligibility validation."""
    # Policy exists
    res = client.get("/payer/policies/SURAKSHA-HEALTH-2026-001")
    assert res.status_code == 200
    assert res.json()["sum_insured"] == 50000000

    # Eligible treatment check
    el_res = client.post("/payer/eligibility", json={
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma",
        "treatment_date": "2026-10-10"
    })
    assert el_res.status_code == 200
    assert el_res.json()["eligible"] is True

    # Member not covered check
    el_fail = client.post("/payer/eligibility", json={
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Unknown Person",
        "treatment_date": "2026-10-10"
    })
    assert el_fail.status_code == 200
    assert el_fail.json()["eligible"] is False


def test_claim_submission_idempotency_and_recovery():
    """Test idempotency guarantee, conflict detection, and client_reference search."""
    payload = {
        "client_reference": "CLIENT-TX-9901",
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma",
        "claim_type": "reimbursement",
        "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05",
        "claimed_amount": 5000000,
        "line_items": [
            {"head": "Room Rent", "amount": 1500000},
            {"head": "Surgeon Fees", "amount": 3500000}
        ]
    }

    # 1. First submission with idempotency key
    headers = {**API_HEADERS, "Idempotency-Key": "IDEM-KEY-001"}
    res1 = client.post("/payer/claims", json=payload, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    claim_id = data1["id"]

    # 2. Replay with identical key and payload -> returns identical response
    res2 = client.post("/payer/claims", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["id"] == claim_id

    # 3. Same key with different payload -> 409 IDEMPOTENCY_CONFLICT
    modified_payload = {**payload, "claimed_amount": 9000000}
    res3 = client.post("/payer/claims", json=modified_payload, headers=headers)
    assert res3.status_code == 409

    # 4. Search by client_reference for lost response recovery
    search_res = client.get("/payer/claims?client_reference=CLIENT-TX-9901")
    assert search_res.status_code == 200
    claims = search_res.json()
    assert len(claims) == 1
    assert claims[0]["id"] == claim_id


def test_claim_query_decide_and_pay_lifecycle():
    """Test full progression: submit -> query -> answer -> decide -> pay -> reopen."""
    # 1. Submit claim
    payload = {
        "client_reference": "CLIENT-TX-LIFECYCLE",
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma",
        "claim_type": "reimbursement",
        "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05",
        "claimed_amount": 5000000,
        "line_items": [{"head": "Hospital Treatment", "amount": 5000000}]
    }
    submit_res = client.post("/payer/claims", json=payload, headers=API_HEADERS)
    claim_id = submit_res.json()["id"]

    # 2. Operator raises query
    query_res = client.post(f"/payer/claims/{claim_id}/query", json={
        "items": [{"code": "DOC_BILL", "label": "Pharmacy Bill", "description": "Original pharmacy receipt"}]
    })
    assert query_res.status_code == 200
    assert query_res.json()["status"] == "query_raised"

    # 3. Member answers query
    answer_res = client.post(f"/payer/claims/{claim_id}/documents", json={
        "documents": [{"doc_type": "pharmacy_bill", "filename": "receipt.pdf"}]
    })
    assert answer_res.status_code == 200
    assert answer_res.json()["status"] == "under_review"

    # 4. Operator decides claim (partially approved)
    decide_res = client.post(f"/payer/claims/{claim_id}/decide", json={
        "outcome": "partially_approved",
        "line_decisions": [
            {"head": "Hospital Treatment", "claimed": 5000000, "approved": 4000000, "policy_clause": "Clause 3.1 (Deduction)"}
        ]
    })
    assert decide_res.status_code == 200
    assert decide_res.json()["status"] == "partially_approved"
    assert decide_res.json()["approved_amount"] == 4000000

    # 5. Operator advises payment
    pay_res = client.post(f"/payer/claims/{claim_id}/pay", json={
        "payee": "member",
        "bank_account_last4": "8921"
    })
    assert pay_res.status_code == 200
    assert pay_res.json()["status"] == "payment_advised"

    # 6. Reopen claim
    reopen_res = client.post(f"/payer/claims/{claim_id}/reopen")
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "reopened"

    # 7. Admin overview returns enriched claims, policies, clock, faults, scenarios, and events
    ov_res = client.get("/admin/overview")
    assert ov_res.status_code == 200
    ov = ov_res.json()
    assert ov["mock"] is True
    assert len(ov["policies"]) >= 1
    assert any(c["id"] == claim_id and c["decision"] is not None for c in ov["claims"])

    # 8. Payer PDF download works for generated decision letter and policy schedule
    letter_doc_id = decide_res.json()["letter_doc_id"]
    pdf_res = client.get(f"/payer/documents/{letter_doc_id}.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content.startswith(b"%PDF")
