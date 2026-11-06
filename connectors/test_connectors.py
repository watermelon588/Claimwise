"""Verify the demo's trust boundary and all four existing mock read contracts."""

from datetime import datetime, timedelta, timezone
from threading import Event, Thread

import httpx
import pytest
from fastapi.testclient import TestClient
from mocks.config import settings
from mocks.faults import FaultsModel, set_faults
from mocks.db import get_connection
from mocks.main import app as mock_app
from mocks.services.scenarios import load_scenario

from connectors.app import DemoKeys, create_app


@pytest.fixture
def demo():
    """Provide fresh synthetic credentials and a gateway factory for each test."""
    keys = DemoKeys()

    def client(transport=None):
        """Open the gateway using its allowed local host and injected transport."""
        return TestClient(create_app(keys, transport), base_url="http://127.0.0.1:8101")

    return keys, client


def verify(client, keys):
    """Verify a browser and return its server-side tool catalog URL."""
    response = client.post("/api/connectors/session", json={"code": keys.onboarding})
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    return f"/agent/cases/{response.json()['case_id']}/tools"


def consent(client, keys, provider):
    """Authenticate and approve one provider for the verified browser."""
    response = client.post(
        f"/api/connectors/{provider}", json={"code": keys.providers[provider], "approved": True},
    )
    assert response.status_code == 200


def test_credentials_consent_and_case_isolation(demo):
    """Deny unverified and cross-case access and keep credentials out of responses."""
    keys, client = demo
    bearer = {"Authorization": f"Bearer {keys.agent}"}
    with client() as browser:
        payload = {"code": keys.providers["insurer"], "approved": True}
        assert browser.get("/").status_code == 200
        assert browser.post("/api/connectors/insurer", json=payload).status_code == 401
        assert browser.post("/api/connectors/session", json={"code": "wrong"}).status_code == 403
        tools = verify(browser, keys)
        first_cookie = browser.cookies.get("claimwise_connector_demo")
        assert browser.get(tools).status_code == 401
        assert browser.get(tools, headers=bearer).json() == {"tools": []}
        assert browser.post("/api/connectors/bank", json=payload).status_code == 403
        assert browser.post("/api/connectors/insurer", json={**payload, "approved": False}).status_code == 403
        assert browser.post("/api/connectors/insurer", json={**payload, "approved": "true"}).status_code == 422
        blocked = browser.post("/api/connectors/insurer", json=payload, headers={"Origin": "http://localhost:9999"})
        assert blocked.status_code == 403
        consent(browser, keys, "insurer")
        assert browser.get(tools, headers=bearer).json()["tools"][0]["name"] == "read_policy"
        assert keys.agent not in browser.get("/api/connectors").text
        assert browser.get(f"{tools}/read_claim", headers=bearer).status_code == 403
        assert browser.get(f"{tools}/read_policy?policy_id=POL-002", headers=bearer).status_code == 422
        assert browser.get(f"{tools}/admin", headers=bearer).status_code == 404

        browser.cookies.clear()
        other_tools = verify(browser, keys)
        assert browser.get(other_tools, headers=bearer).json() == {"tools": []}
        assert browser.get(f"{other_tools}/read_policy", headers=bearer).status_code == 403
        forged_cookie = browser.cookies.get("claimwise_connector_demo").split(".")[0] + "." + first_cookie.split(".")[1]
        denied = browser.get("/api/connectors", headers={"Cookie": f"claimwise_connector_demo={forged_cookie}"})
        assert denied.status_code == 401
        assert browser.delete("/api/connectors/session").status_code == 204
        assert browser.get(other_tools, headers=bearer).status_code == 401


def test_reads_against_existing_mock_service(demo, monkeypatch, tmp_path):
    """Seed a disposable mock workspace and read real policy, claim, PDF and credit responses."""
    keys, client = demo
    monkeypatch.setattr(settings, "mock_db_path", str(tmp_path / "mock.db"))
    monkeypatch.setattr(settings, "docs_storage_path", str(tmp_path / "docs"))
    load_scenario("standard_reimbursement")
    connection = get_connection()
    try:
        # Keep fixture creation from dispatching anything to a running Claimwise backend.
        set_faults(FaultsModel(webhook_down=True), connection)
    finally:
        connection.close()
    mock_headers = {"X-Api-Key": settings.api_keys_list[0]}
    with TestClient(mock_app) as operator:
        discharged = operator.post(
            "/hospital/admissions/ADM-001/discharge", params={"discharge_date": "2026-10-05"},
            headers=mock_headers,
        )
        assert discharged.status_code == 200
        credit = operator.post(
            "/bank/accounts/ACC-001/credits", headers=mock_headers,
            json={"amount": 4230000, "utr": "UTR-SYNTHETIC", "narration": "Synthetic settlement"},
        )
        assert credit.status_code == 200

    bearer = {"Authorization": f"Bearer {keys.agent}"}
    with client(httpx.ASGITransport(app=mock_app)) as browser:
        tools = verify(browser, keys)
        for provider in keys.providers:
            consent(browser, keys, provider)
        assert len(browser.get(tools, headers=bearer).json()["tools"]) == 4
        policy = browser.get(f"{tools}/read_policy", headers=bearer).json()
        assert policy["source"]["mock"] is True
        assert policy["data"]["sum_insured"] == 50000000
        assert "members" not in policy["data"]
        claim = browser.get(f"{tools}/read_claim", headers=bearer).json()
        assert claim["source"]["provider"] == "tpa"
        assert claim["data"]["id"] == "CLM-0001"
        pdf = browser.get(f"{tools}/read_discharge_summary", headers=bearer)
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.headers["x-connector-provider"] == "hospital"
        assert pdf.content.startswith(b"%PDF-")
        bank = browser.get(f"{tools}/read_bank_credits", headers=bearer).json()
        assert bank["data"]["credits"][0]["amount"] == 4230000
        assert bank["data"]["account"] == {"id": "ACC-001"}
        assert browser.delete("/api/connectors/bank").status_code == 204
        assert browser.get(f"{tools}/read_bank_credits", headers=bearer).status_code == 403
        assert browser.get(f"{tools}/read_policy", headers=bearer).status_code == 200


@pytest.mark.parametrize(("status", "expected"), [(404, 404), (302, 502), (503, 503), (200, 502)])
def test_bad_upstream_response_is_bounded(demo, status, expected):
    """Hide upstream payloads and reject redirects, missing records and malformed data."""
    keys, client = demo
    bearer = {"Authorization": f"Bearer {keys.agent}"}
    transport = httpx.MockTransport(
        lambda _: httpx.Response(status, json={"private": "provider-only"}, headers={"Location": "/admin"}),
    )
    with client(transport) as browser:
        tools = verify(browser, keys)
        consent(browser, keys, "insurer")
        result = browser.get(f"{tools}/read_policy", headers=bearer)
        assert result.status_code == expected
        assert "provider-only" not in result.text


def test_revocation_blocks_an_in_flight_read(demo):
    """Drop a pending read even when the user reconnects before the response arrives."""
    keys, client = demo
    started, release = Event(), Event()
    bearer = {"Authorization": f"Bearer {keys.agent}"}

    async def pending_pdf(_request):
        """Pause the provider response until the test has replaced the grant."""
        import asyncio

        started.set()
        assert await asyncio.to_thread(release.wait, 5)
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%PDF-demo")

    with client(httpx.MockTransport(pending_pdf)) as browser:
        tools = verify(browser, keys)
        consent(browser, keys, "hospital")
        result = []
        call = Thread(target=lambda: result.append(browser.get(f"{tools}/read_discharge_summary", headers=bearer)))
        call.start()
        try:
            assert started.wait(5)
            assert browser.delete("/api/connectors/hospital").status_code == 204
            consent(browser, keys, "hospital")
        finally:
            release.set()
            call.join(5)
        assert result and result[0].status_code == 403


def test_submit_claim_is_idempotent_and_recoverable(demo, monkeypatch, tmp_path):
    """Submit needs TPA consent; a lost response is found by client reference and a retry is not a duplicate."""
    keys, client = demo
    monkeypatch.setattr(settings, "mock_db_path", str(tmp_path / "mock.db"))
    monkeypatch.setattr(settings, "docs_storage_path", str(tmp_path / "docs"))
    load_scenario("standard_reimbursement")
    connection = get_connection()
    try:
        set_faults(FaultsModel(webhook_down=True, drop_response_after_commit=True), connection)
    finally:
        connection.close()
    body = {
        "client_reference": "cw-thread-1-abcdef12", "policy_number": "SURAKSHA-HEALTH-2026-001",
        "member_name": "Ramesh Sharma", "claim_type": "reimbursement", "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05", "claimed_amount": 8500000,
        "line_items": [{"head": "Room", "amount": 8500000}],
        "documents": [{"id": "d1", "filename": "bill.pdf", "doc_type": "hospital_bill"}],
    }
    bearer = {"Authorization": f"Bearer {keys.agent}"}
    with client(httpx.ASGITransport(app=mock_app, raise_app_exceptions=False)) as browser:
        claims = verify(browser, keys).removesuffix("/tools") + "/claims"
        headers = {**bearer, "Idempotency-Key": "key-thread-1-abcdef12"}
        assert browser.post(claims, json=body, headers=headers).status_code == 403
        consent(browser, keys, "tpa")
        assert browser.post(claims, json={**body, "extra": 1}, headers=headers).status_code == 422
        # The payer commits, then the response is lost.
        lost = browser.post(claims, json=body, headers=headers)
        assert lost.json()["detail"]["code"] == "PROVIDER_SUBMIT_UNCONFIRMED"
        found = browser.get(claims, params={"client_reference": body["client_reference"]}, headers=bearer).json()
        [claim] = found["data"]
        # A retry with the same key returns the same claim instead of creating a second one.
        retry = browser.post(claims, json=body, headers=headers).json()["data"]
        assert retry["id"] == claim["id"]
        assert len(browser.get(claims, params={"client_reference": body["client_reference"]}, headers=bearer).json()["data"]) == 1
        status = browser.get(f"{claims}/{claim['id']}", headers=bearer).json()
        assert status["data"]["status"] == "submitted" and status["source"]["tool"] == "read_submitted_claim"
        assert browser.get(f"{claims}/../x", headers=bearer).status_code in (404, 422)
        refused = browser.post(claims, json={**body, "client_reference": "cw-other-ref-0001", "member_name": "Nobody"},
                               headers={**bearer, "Idempotency-Key": "key-other-ref-0001"})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "MEMBER_NOT_COVERED"


def test_answer_query_needs_consent_and_an_open_query(demo, monkeypatch, tmp_path):
    """Answering a query needs TPA consent and an open query; the payer then marks the query answered."""
    keys, client = demo
    monkeypatch.setattr(settings, "mock_db_path", str(tmp_path / "mock.db"))
    monkeypatch.setattr(settings, "docs_storage_path", str(tmp_path / "docs"))
    load_scenario("standard_reimbursement")
    connection = get_connection()
    try:
        set_faults(FaultsModel(webhook_down=True), connection)
    finally:
        connection.close()
    bearer = {"Authorization": f"Bearer {keys.agent}"}
    answer = {"documents": [{"id": "d1", "filename": "lab.pdf", "doc_type": "investigation_report"}]}
    with client(httpx.ASGITransport(app=mock_app, raise_app_exceptions=False)) as browser:
        docs = verify(browser, keys).removesuffix("/tools") + "/claims/CLM-0001/documents"
        assert browser.post(docs, json=answer, headers=bearer).status_code == 403
        consent(browser, keys, "tpa")
        assert browser.post(docs, json=answer, headers=bearer).json()["detail"]["code"] == "QUERY_NOT_OPEN"
        with TestClient(mock_app) as payer:
            payer.post("/payer/claims/CLM-0001/query", json={"items": [{"code": "lab", "label": "Lab reports"}]})
        assert browser.post(docs, json={"documents": []}, headers=bearer).status_code == 422
        sent = browser.post(docs, json=answer, headers=bearer)
        assert sent.status_code == 200 and sent.json()["data"]["status"] == "under_review"
        assert sent.json()["source"]["tool"] == "answer_query"


def test_workspace_consent_and_demo_mail(demo):
    """Reject cross-thread claims and deliver generic messages once until consent is removed."""
    keys, client = demo
    workspace = {"X-Claimwise-Thread": "claim-one"}
    other = {"X-Claimwise-Thread": "claim-two"}
    with client() as browser:
        verified = browser.post("/api/connectors/session", json={"code": keys.onboarding}, headers=workspace)
        assert verified.status_code == 201
        case = f"/agent/cases/{verified.json()['case_id']}"
        server = {"Authorization": f"Bearer {keys.agent}"}
        assert browser.get("/api/connectors", headers=other).status_code == 401
        assert browser.get(f"{case}/tools", headers={**server, **other}).status_code == 403
        assert browser.get(f"{case}/tools", headers=server).status_code == 403

        email = "/api/connectors/email"
        assert browser.post(email, json={"code": keys.email, "approved": False}, headers=workspace).status_code == 403
        assert browser.post(email, json={"code": keys.email, "approved": True}, headers=workspace).status_code == 200
        assert browser.get(f"{case}/tools", headers={**server, **workspace}).json()["tools"][0]["name"] == "case_email"
        assert browser.get("/api/connectors/document", headers=workspace).status_code == 403
        now = datetime.now(timezone.utc)
        payload = {"notices": [
            {"id": "a" * 64, "at": now.isoformat(), "kind": "update"},
            {"id": "b" * 64, "at": (now - timedelta(days=1)).isoformat(), "kind": "reminder"},
        ]}
        for _ in range(2):
            assert browser.post(f"{case}/mail", json=payload, headers=server).status_code == 200
        messages = browser.get("/api/connectors/inbox", headers=workspace).json()["messages"]
        assert [m["id"] for m in messages] == ["a" * 64]
        assert set(messages[0]) == {"id", "at", "subject", "body"}
        assert browser.delete(email, headers=workspace).status_code == 204
        assert browser.get("/api/connectors/inbox", headers=workspace).status_code == 403
        assert browser.post(f"{case}/mail", json=payload, headers=server).status_code == 403
