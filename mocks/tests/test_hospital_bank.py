"""Integration tests for hospital admissions and bank account services."""

import pytest
from fastapi.testclient import TestClient
from mocks.main import app
from mocks.services.scenarios import reset_database

client = TestClient(app)
API_HEADERS = {"X-Api-Key": "hospital-demo-key"}


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()


def test_hospital_admission_discharge_and_reissue():
    """Verify hospital workflow: admission -> discharge -> document download -> reissue."""
    # 1. Create admission
    adm_res = client.post("/hospital/admissions", json={
        "hospital_id": "HOSP-001",
        "patient_name": "Sunita Sharma",
        "policy_number": "SURAKSHA-HEALTH-2026-001",
        "admission_date": "2026-10-10",
        "diagnosis_text": "Cholecystitis",
        "deposit_amount": 500000
    }, headers=API_HEADERS)
    assert adm_res.status_code == 200
    adm_id = adm_res.json()["admission_id"]

    # 2. Discharge patient
    dis_res = client.post(f"/hospital/admissions/{adm_id}/discharge?discharge_date=2026-10-12", headers=API_HEADERS)
    assert dis_res.status_code == 200
    ds_doc_id = dis_res.json()["discharge_summary_doc_id"]

    # 3. Download document PDF
    dl_res = client.get(f"/hospital/documents/{ds_doc_id}.pdf")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/pdf"
    assert len(dl_res.content) > 100

    # 4. Reissue corrected document
    reissue_res = client.post(f"/hospital/documents/{ds_doc_id}/reissue", json={
        "corrected_diagnosis": "Cholecystitis (Symptom duration 5 days)"
    })
    assert reissue_res.status_code == 200
    assert reissue_res.json()["version"] == 2


def test_bank_credit_and_statement_pdf():
    """Verify posting a credit to an account and retrieving statement PDF."""
    headers = {"X-Api-Key": "claimwise-demo-key"}

    # 1. Post credit
    credit_res = client.post("/bank/accounts/ACC-001/credits", json={
        "amount": 4500000,
        "utr": "UTR-TEST-SETTLE-001",
        "narration": "NEFT SETTLEMENT SURAKSHA"
    }, headers=headers)
    assert credit_res.status_code == 200

    # 2. Get JSON statement
    stmt_res = client.get("/bank/accounts/ACC-001/statement")
    assert stmt_res.status_code == 200
    assert stmt_res.json()["total_credits"] >= 4500000

    # 3. Get PDF statement
    pdf_res = client.get("/bank/accounts/ACC-001/statement.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 100
