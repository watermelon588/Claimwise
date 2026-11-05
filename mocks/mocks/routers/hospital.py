"""Hospital service router for admissions, cashless pre-auth, and billing."""

import json
import os
import sqlite3
import uuid
from typing import Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from mocks.auth import verify_api_key
from mocks.clock import get_current_time_iso
from mocks.db import get_connection, row_to_dict
from mocks.events import record_and_dispatch_event
from mocks.services.pdf_generator import (
    generate_discharge_summary_pdf,
    generate_final_bill_pdf,
)

router = APIRouter(prefix="/hospital", tags=["Hospital Service (M2)"])


class AdmissionCreateRequest(BaseModel):
    """Operator payload to register an in-patient hospital admission."""

    hospital_id: str = "HOSP-001"
    patient_name: str
    policy_number: str
    admission_date: str
    diagnosis_text: str
    deposit_amount: int = Field(default=0, ge=0, description="Security deposit in paise")


class ReissueDocumentRequest(BaseModel):
    """Payload to reissue a corrected hospital document."""

    corrected_diagnosis: str | None = None
    corrected_line_items: list[dict[str, Any]] | None = None


@router.post("/admissions")
def create_admission(req: AdmissionCreateRequest, api_key: str = Depends(verify_api_key)) -> dict:
    """Create a new hospital admission record."""
    conn = get_connection()
    try:
        admission_id = f"ADM-{uuid.uuid4().hex[:8].upper()}"
        conn.execute("""
        INSERT INTO admissions (
            id, hospital_id, patient_name, policy_number, admission_date,
            diagnosis_text, status, deposit_amount, deposit_status
        ) VALUES (?, ?, ?, ?, ?, ?, 'admitted', ?, 'held');
        """, (
            admission_id, req.hospital_id, req.patient_name, req.policy_number,
            req.admission_date, req.diagnosis_text, req.deposit_amount
        ))
        conn.commit()

        return {
            "admission_id": admission_id,
            "status": "admitted",
            "deposit_amount": req.deposit_amount,
            "deposit_status": "held",
            "mock": True
        }
    finally:
        conn.close()


@router.post("/admissions/{admission_id}/discharge")
def discharge_patient(admission_id: str, discharge_date: str, api_key: str = Depends(verify_api_key)) -> dict:
    """Discharge patient and issue initial discharge summary and final bill PDFs."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM admissions WHERE id = ?;", (admission_id,))
        a_row = cur.fetchone()
        if not a_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Admission {admission_id} not found", "retryable": False}})
        admission = row_to_dict(a_row)

        cur.execute("SELECT * FROM hospitals WHERE id = ?;", (admission["hospital_id"],))
        h_row = cur.fetchone()
        hospital = row_to_dict(h_row) if h_row else {"name": "Sunrise Hospital (MOCK)", "city": "New Delhi"}

        now = get_current_time_iso(conn)

        # Update admission status
        conn.execute("UPDATE admissions SET discharge_date = ?, status = 'discharged' WHERE id = ?;", (discharge_date, admission_id))
        admission["discharge_date"] = discharge_date

        # Issue Discharge Summary
        ds_doc_id = f"DOC-DS-{admission_id}"
        ds_path = generate_discharge_summary_pdf(ds_doc_id, admission, hospital, version=1)
        conn.execute("""
        INSERT OR REPLACE INTO hospital_documents (id, admission_id, doc_type, version, issued_at, file_path)
        VALUES (?, ?, 'discharge_summary', 1, ?, ?);
        """, (ds_doc_id, admission_id, now, ds_path))

        # Issue Final Bill
        bill_doc_id = f"DOC-BILL-{admission_id}"
        sample_lines = [
            {"head": "Room & Nursing Charges", "amount": 1500000},
            {"head": "Operation Theatre & Surgeon Charges", "amount": 3500000},
            {"head": "Pharmacy & Consumables", "amount": 1000000}
        ]
        bill_path = generate_final_bill_pdf(bill_doc_id, admission, hospital, sample_lines)
        conn.execute("""
        INSERT OR REPLACE INTO hospital_documents (id, admission_id, doc_type, version, issued_at, file_path)
        VALUES (?, ?, 'final_bill', 1, ?, ?);
        """, (bill_doc_id, admission_id, now, bill_path))

        conn.commit()

        record_and_dispatch_event("hospital.document_issued", "admission", admission_id, 1, {
            "admission_id": admission_id,
            "discharge_summary_doc_id": ds_doc_id,
            "final_bill_doc_id": bill_doc_id
        }, conn)

        return {
            "admission_id": admission_id,
            "status": "discharged",
            "discharge_summary_doc_id": ds_doc_id,
            "final_bill_doc_id": bill_doc_id,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/documents/{doc_id}/reissue")
def reissue_document(doc_id: str, req: ReissueDocumentRequest) -> dict:
    """Reissue a corrected version of a hospital document (version + 1)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM hospital_documents WHERE id = ?;", (doc_id,))
        d_row = cur.fetchone()
        if not d_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Document {doc_id} not found", "retryable": False}})
        doc = row_to_dict(d_row)

        cur.execute("SELECT * FROM admissions WHERE id = ?;", (doc["admission_id"],))
        admission = row_to_dict(cur.fetchone())

        cur.execute("SELECT * FROM hospitals WHERE id = ?;", (admission["hospital_id"],))
        hospital = row_to_dict(cur.fetchone()) or {"name": "Sunrise Hospital (MOCK)", "city": "New Delhi"}

        now = get_current_time_iso(conn)
        new_version = doc["version"] + 1

        if req.corrected_diagnosis:
            admission["diagnosis_text"] = req.corrected_diagnosis

        new_doc_id = f"{doc_id}-v{new_version}"
        if doc["doc_type"] == "discharge_summary":
            new_path = generate_discharge_summary_pdf(new_doc_id, admission, hospital, version=new_version)
        else:
            lines = req.corrected_line_items or [{"head": "Reissued Hospital Charges", "amount": 5000000}]
            new_path = generate_final_bill_pdf(new_doc_id, admission, hospital, lines)

        conn.execute("""
        INSERT INTO hospital_documents (id, admission_id, doc_type, version, issued_at, file_path)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (new_doc_id, doc["admission_id"], doc["doc_type"], new_version, now, new_path))
        conn.commit()

        return {
            "original_doc_id": doc_id,
            "reissued_doc_id": new_doc_id,
            "version": new_version,
            "mock": True
        }
    finally:
        conn.close()


@router.get("/documents/{doc_id}.pdf")
def download_document_pdf(doc_id: str):
    """Download a generated hospital document PDF for uploading into Claimwise."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT file_path FROM hospital_documents WHERE id = ?;", (doc_id,))
        row = cur.fetchone()
        if not row or not os.path.exists(row["file_path"]):
            raise HTTPException(status_code=404, detail="Document PDF file not found on disk")
        return FileResponse(row["file_path"], media_type="application/pdf", filename=f"{doc_id}.pdf")
    finally:
        conn.close()
