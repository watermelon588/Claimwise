"""Grievance and Ombudsman service router for insurer escalations."""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from mocks.auth import verify_api_key
from mocks.clock import get_current_time_iso
from mocks.db import get_connection, row_to_dict
from mocks.events import record_and_dispatch_event

router = APIRouter(prefix="/grievance", tags=["Grievance & Ombudsman (M4)"])


class GrievanceFileRequest(BaseModel):
    """Payload to lodge an administrative grievance with the insurer or Bima Bharosa."""

    claim_id: str
    level: str = Field(default="insurer_gro", description="insurer_gro or bima_bharosa")
    complaint_text: str


class OmbudsmanComplaintRequest(BaseModel):
    """Payload to register an escalation complaint with the Insurance Ombudsman."""

    grievance_id: str
    claim_id: str
    complaint_summary: str


class ResolveGrievanceRequest(BaseModel):
    """Operator payload to resolve a lodged grievance."""

    status: str = Field(description="resolved or rejected")
    resolution_text: str


class OmbudsmanAwardRequest(BaseModel):
    """Operator payload to pronounce an Ombudsman award."""

    award_amount: int = Field(ge=0, description="Awarded sum in paise")
    award_notes: str
    reopen_claim: bool = True


@router.post("/grievances")
def file_grievance(req: GrievanceFileRequest, api_key: str = Depends(verify_api_key)) -> dict:
    """File a formal grievance against a claim decision or delay."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (req.claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "CLAIM_NOT_FOUND", "message": f"Claim {req.claim_id} not found", "retryable": False}})

        grievance_id = f"GRV-{uuid.uuid4().hex[:8].upper()}"
        now_str = get_current_time_iso(conn)
        now_dt = datetime.fromisoformat(now_str)
        due_dt = now_dt + timedelta(days=14)
        due_str = due_dt.isoformat()

        conn.execute("""
        INSERT INTO grievances (
            id, level, claim_id, filed_at, acknowledged_at, due_at, status, resolution_text
        ) VALUES (?, ?, ?, ?, ?, ?, 'acknowledged', '');
        """, (grievance_id, req.level, req.claim_id, now_str, now_str, due_str))
        conn.commit()

        record_and_dispatch_event("grievance.acknowledged", "grievance", grievance_id, 1, {
            "grievance_id": grievance_id,
            "claim_id": req.claim_id,
            "due_at": due_str
        }, conn)

        return {
            "grievance_id": grievance_id,
            "claim_id": req.claim_id,
            "level": req.level,
            "status": "acknowledged",
            "acknowledged_at": now_str,
            "due_at": due_str,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/grievances/{grievance_id}/resolve")
def resolve_grievance(grievance_id: str, req: ResolveGrievanceRequest) -> dict:
    """Operator action: Resolve or repudiate a customer grievance."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM grievances WHERE id = ?;", (grievance_id,))
        g_row = cur.fetchone()
        if not g_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Grievance {grievance_id} not found", "retryable": False}})

        conn.execute("UPDATE grievances SET status = ?, resolution_text = ? WHERE id = ?;", (req.status, req.resolution_text, grievance_id))
        conn.commit()

        record_and_dispatch_event("grievance.resolved", "grievance", grievance_id, 2, {
            "grievance_id": grievance_id,
            "status": req.status,
            "resolution_text": req.resolution_text
        }, conn)

        return {
            "grievance_id": grievance_id,
            "status": req.status,
            "resolution_text": req.resolution_text,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/ombudsman")
def file_ombudsman_complaint(req: OmbudsmanComplaintRequest, api_key: str = Depends(verify_api_key)) -> dict:
    """File an escalation complaint with the Insurance Ombudsman with eligibility verification."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Verify grievance exists
        cur.execute("SELECT * FROM grievances WHERE id = ?;", (req.grievance_id,))
        g_row = cur.fetchone()
        if not g_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "GRIEVANCE_NOT_FOUND", "message": f"Grievance {req.grievance_id} not found", "retryable": False}})
        grievance = row_to_dict(g_row)

        # Verify claim and claimed amount
        cur.execute("SELECT * FROM claims WHERE id = ?;", (req.claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "CLAIM_NOT_FOUND", "message": f"Claim {req.claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        now_str = get_current_time_iso(conn)
        now_dt = datetime.fromisoformat(now_str)
        filed_dt = datetime.fromisoformat(grievance["filed_at"])
        days_since_grievance = (now_dt - filed_dt).days

        # Rule 1: Limit up to Rs 50 Lakh (5,000,000,00 paise)
        eligible = True
        eligibility_reason = "Complaint satisfies Insurance Ombudsman rules"

        if claim["claimed_amount"] > 500000000:
            eligible = False
            eligibility_reason = "Claim amount exceeds Insurance Ombudsman pecuniary limit of Rs 50 Lakh"
        elif grievance["status"] != "resolved" and days_since_grievance < 30:
            eligible = False
            eligibility_reason = f"Insurer has not replied and 30 days have not elapsed since filing grievance ({days_since_grievance} days passed)"

        ombudsman_id = f"OMB-{uuid.uuid4().hex[:8].upper()}"
        initial_status = "registered" if eligible else "rejected"

        conn.execute("""
        INSERT INTO ombudsman_complaints (
            id, grievance_id, claim_id, filed_at, eligible, eligibility_reason,
            status, award_amount, award_issued_at, compliance_due_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL);
        """, (
            ombudsman_id, req.grievance_id, req.claim_id, now_str,
            1 if eligible else 0, eligibility_reason, initial_status
        ))
        conn.commit()

        if eligible:
            record_and_dispatch_event("ombudsman.registered", "ombudsman", ombudsman_id, 1, {
                "ombudsman_id": ombudsman_id,
                "claim_id": req.claim_id,
                "status": initial_status
            }, conn)

        return {
            "ombudsman_id": ombudsman_id,
            "eligible": eligible,
            "eligibility_reason": eligibility_reason,
            "status": initial_status,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/ombudsman/{ombudsman_id}/award")
def issue_ombudsman_award(ombudsman_id: str, req: OmbudsmanAwardRequest) -> dict:
    """Operator action: Pronounce Ombudsman award and trigger claim reopening."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ombudsman_complaints WHERE id = ?;", (ombudsman_id,))
        o_row = cur.fetchone()
        if not o_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Ombudsman case {ombudsman_id} not found", "retryable": False}})
        case = row_to_dict(o_row)

        now_str = get_current_time_iso(conn)
        now_dt = datetime.fromisoformat(now_str)
        compliance_due = (now_dt + timedelta(days=30)).isoformat()

        conn.execute("""
        UPDATE ombudsman_complaints SET
            status = 'award_issued',
            award_amount = ?,
            award_issued_at = ?,
            compliance_due_at = ?
        WHERE id = ?;
        """, (req.award_amount, now_str, compliance_due, ombudsman_id))

        # If reopen_claim requested, reopen in payer M1
        if req.reopen_claim:
            conn.execute("UPDATE claims SET status = 'reopened', updated_at = ? WHERE id = ?;", (now_str, case["claim_id"]))

        conn.commit()

        record_and_dispatch_event("ombudsman.award_issued", "ombudsman", ombudsman_id, 2, {
            "ombudsman_id": ombudsman_id,
            "claim_id": case["claim_id"],
            "award_amount": req.award_amount,
            "compliance_due_at": compliance_due,
            "claim_reopened": req.reopen_claim
        }, conn)

        return {
            "ombudsman_id": ombudsman_id,
            "status": "award_issued",
            "award_amount": req.award_amount,
            "compliance_due_at": compliance_due,
            "claim_reopened": req.reopen_claim,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/ombudsman/{ombudsman_id}/comply")
def comply_ombudsman_award(ombudsman_id: str, complied: bool = True) -> dict:
    """Operator action: Record insurer compliance status against Ombudsman award."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ombudsman_complaints WHERE id = ?;", (ombudsman_id,))
        o_row = cur.fetchone()
        if not o_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Ombudsman case {ombudsman_id} not found", "retryable": False}})

        new_status = "complied" if complied else "not_complied"
        conn.execute("UPDATE ombudsman_complaints SET status = ? WHERE id = ?;", (new_status, ombudsman_id))
        conn.commit()

        record_and_dispatch_event("ombudsman.award_complied", "ombudsman", ombudsman_id, 3, {
            "ombudsman_id": ombudsman_id,
            "status": new_status
        }, conn)

        return {
            "ombudsman_id": ombudsman_id,
            "status": new_status,
            "mock": True
        }
    finally:
        conn.close()
