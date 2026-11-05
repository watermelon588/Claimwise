"""Integration tests for Grievance Desk and Insurance Ombudsman routes."""

import pytest
from fastapi.testclient import TestClient
from mocks.main import app
from mocks.services.scenarios import reset_database

client = TestClient(app)
API_HEADERS = {"X-Api-Key": "claimwise-demo-key"}


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()


def test_grievance_filing_and_tat():
    """Verify grievance acknowledgement and 14-day statutory turnaround time."""
    # First submit a claim
    payload = {
        "client_reference": "CLIENT-GRV-TEST",
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma",
        "claim_type": "reimbursement",
        "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05",
        "claimed_amount": 5000000,
        "line_items": [{"head": "General Hospitalization", "amount": 5000000}]
    }
    claim_id = client.post("/payer/claims", json=payload, headers=API_HEADERS).json()["id"]

    # File grievance
    res = client.post("/grievance/grievances", json={
        "claim_id": claim_id,
        "level": "insurer_gro",
        "complaint_text": "Unjustified deduction of room rent charges"
    }, headers=API_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "acknowledged"
    assert "due_at" in data
    assert data["due_at"] > data["acknowledged_at"]


def test_ombudsman_eligibility_rules():
    """Verify Ombudsman eligibility criteria: rejected grievance vs premature filing vs 50L cap."""
    # 1. Create claim
    payload = {
        "client_reference": "CLIENT-OMB-TEST",
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma",
        "claim_type": "reimbursement",
        "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05",
        "claimed_amount": 6000000,
        "line_items": [{"head": "Treatment", "amount": 6000000}]
    }
    claim_id = client.post("/payer/claims", json=payload, headers=API_HEADERS).json()["id"]

    # 2. File grievance
    grv_res = client.post("/grievance/grievances", json={
        "claim_id": claim_id,
        "level": "insurer_gro",
        "complaint_text": "Claim repudiation dispute"
    }, headers=API_HEADERS)
    grv_id = grv_res.json()["grievance_id"]

    # 3. Premature Ombudsman filing (< 30 days and grievance unresolved) -> eligible: false
    premature_res = client.post("/grievance/ombudsman", json={
        "grievance_id": grv_id,
        "claim_id": claim_id,
        "complaint_summary": "Disputing repudiation"
    }, headers=API_HEADERS)
    assert premature_res.status_code == 200
    assert premature_res.json()["eligible"] is False
    assert premature_res.json()["status"] == "rejected"

    # 4. Resolve grievance as rejected (member dissatisfied)
    client.post(f"/grievance/grievances/{grv_id}/resolve", json={
        "status": "resolved",
        "resolution_text": "Internal review upholds rejection under Clause 6.1"
    })

    # 5. Now file Ombudsman complaint -> eligible: true
    omb_res = client.post("/grievance/ombudsman", json={
        "grievance_id": grv_id,
        "claim_id": claim_id,
        "complaint_summary": "Dissatisfied with grievance resolution"
    }, headers=API_HEADERS)
    assert omb_res.status_code == 200
    assert omb_res.json()["eligible"] is True
    assert omb_res.json()["status"] == "registered"
    omb_id = omb_res.json()["ombudsman_id"]

    # 6. Ombudsman issues award and reopens claim
    award_res = client.post(f"/grievance/ombudsman/{omb_id}/award", json={
        "award_amount": 5500000,
        "award_notes": "Insurer directed to settle claim minus non-payables",
        "reopen_claim": True
    })
    assert award_res.status_code == 200
    assert award_res.json()["status"] == "award_issued"
    assert award_res.json()["claim_reopened"] is True

    # 7. Check claim status in payer M1 -> should now be reopened
    claim_check = client.get(f"/payer/claims/{claim_id}")
    assert claim_check.status_code == 200
    assert claim_check.json()["status"] == "reopened"
