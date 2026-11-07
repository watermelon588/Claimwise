"""Exercise claim pack approval, file views, exports, and regeneration through the API."""

from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pypdf import PdfReader

from app.agent import graph as graph_module, onboarding
from app.config import get_settings
from tests.test_claim import BILL, SUMMARY, base_state

ROOT = Path(__file__).resolve().parents[2]


def test_claim_pack_originals_downloads_and_approval_reset(monkeypatch, tmp_path):
    """Review actual PDF and PNG bytes, approve, and verify an added file invalidates approval."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY2", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()

    class FakeModel:
        """Keep the API integration independent of live model keys."""

        def invoke(self, _messages):
            """Return a short acknowledgement for non-action turns."""
            return AIMessage("Document received.")

    def extract(document):
        """Supply fixed extracted facts for the genuine fixture file bytes."""
        if document["filename"] == "summary.pdf":
            return onboarding.DocumentExtraction(
                doc_type="discharge_summary", hospital=onboarding.HospitalFields(**SUMMARY["facts"]),
            )
        if document["filename"] == "bill.png":
            return onboarding.DocumentExtraction(
                doc_type="hospital_bill", hospital=onboarding.HospitalFields(**BILL["facts"]),
            )
        return onboarding.DocumentExtraction(doc_type="prescription")

    monkeypatch.setattr(graph_module, "get_llm", lambda _tools: FakeModel())
    monkeypatch.setattr(onboarding, "extract_document", extract)
    from app.main import app

    pdf = (ROOT / "mocks/mock_documents/valid/run1_standard_reimbursement/02_discharge_summary.pdf").read_bytes()
    png = (ROOT / "frontend/public/mascot-icon.png").read_bytes()
    thread = "pack-export-smoke"
    endpoint = f"/api/pack/{thread}"

    with TestClient(app) as client:
        def upload(filename, content, mime_type):
            """Upload evidence through the real route and run the graph."""
            response = client.post(
                "/api/documents", data={"thread_id": thread}, files={"file": (filename, content, mime_type)},
            )
            assert response.status_code == 200, response.text
            return response.json()

        client.app.state.graph.update_state({"configurable": {"thread_id": thread}}, base_state())
        assert client.get(endpoint).status_code == 409
        upload("summary.pdf", pdf, "application/pdf")
        upload("bill.png", png, "image/png")

        review = client.post("/api/action", json={"thread_id": thread, "action": "prepare_pack"})
        assert review.status_code == 200, review.text
        assert review.json()["pending"]["type"] == "approve_submission"
        old_hash = review.json()["pending"]["pack"]["hash"]
        approved = client.post("/api/resume", json={"thread_id": thread, "approved": True})
        assert approved.status_code == 200, approved.text
        data = client.get(endpoint).json()
        assert data["status"] == "approved" and data["pack"]["hash"] == old_hash

        for item, original in zip(data["pack"]["documents"], (pdf, png), strict=True):
            viewed = client.get(f"{endpoint}/documents/{item['id']}")
            assert viewed.content == original
            assert viewed.headers["content-disposition"].startswith("inline")
            assert viewed.headers["cache-control"] == "no-store"
        assert client.get(f"{endpoint}/documents/unrelated").status_code == 404

        combined = client.get(f"{endpoint}/pdf")
        assert combined.status_code == 200
        assert old_hash in combined.headers["content-disposition"]
        pages = PdfReader(BytesIO(combined.content)).pages
        assert len(pages) == 2 + len(PdfReader(BytesIO(pdf)).pages)
        assert "Claim pack (approved" in pages[0].extract_text()

        email = client.get(f"{endpoint}/eml")
        assert email.status_code == 200
        draft = BytesParser(policy=policy.default).parsebytes(email.content)
        assert draft["X-Unsent"] == "1" and draft["To"] is None
        assert [(part.get_filename(), part.get_payload(decode=True)) for part in draft.iter_attachments()] == [
            ("summary.pdf", pdf), ("bill.png", png),
        ]

        # Different bytes: the exact same file again would be refused as a duplicate (DEV-023).
        updated = upload("prescription.pdf", pdf + b"%copy", "application/pdf")
        assert "approval_invalidated" in {issue["code"] for issue in updated["claim"]["issues"]}
        changed = client.get(endpoint).json()
        assert changed["status"] == "changed" and changed["pack"]["hash"] != old_hash
        assert len(changed["pack"]["documents"]) == 3
        new_export = client.get(f"{endpoint}/pdf")
        assert changed["pack"]["hash"] in new_export.headers["content-disposition"]
        assert "Claim pack (changed" in PdfReader(BytesIO(new_export.content)).pages[0].extract_text()
        renewed = client.post("/api/action", json={"thread_id": thread, "action": "review_pack"})
        assert renewed.status_code == 200, renewed.text
        assert renewed.json()["pending"]["pack"]["hash"] == changed["pack"]["hash"]
        assert client.post("/api/resume", json={"thread_id": thread, "approved": True}).status_code == 200
        assert client.get(endpoint).json()["status"] == "approved"

    get_settings.cache_clear()
