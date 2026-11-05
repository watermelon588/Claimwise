"""Payer service router for insurer and TPA claim operations."""

import json
import os
import sqlite3
import uuid
from typing import Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Header, Request, Query
from fastapi.responses import FileResponse
from mocks.auth import verify_api_key, check_idempotency, record_idempotency, check_and_apply_drop_fault
from mocks.clock import get_current_time_iso
from mocks.config import settings
from mocks.db import get_connection, row_to_dict
from mocks.events import record_and_dispatch_event
from mocks.services.payer_logic import calculate_line_decisions, validate_decision_clauses
from mocks.services.pdf_generator import (
    ensure_storage_dir,
    generate_policy_pdf,
    generate_query_letter_pdf,
    generate_decision_letter_pdf,
)

router = APIRouter(prefix="/payer", tags=["Payer Service (M1)"])


# Pydantic Request Models
class EligibilityRequest(BaseModel):
    """Payload to check coverage eligibility for a treatment date."""

    policy_number: str
    member_name: str
    treatment_date: str


class PreauthRequest(BaseModel):
    """Cashless pre-authorisation request submitted by a hospital."""

    policy_number: str
    member_name: str
    hospital_id: str
    admission_date: str
    diagnosis_text: str
    estimated_amount: int = Field(gt=0, description="Estimated total in paise")


class LineItem(BaseModel):
    """Itemized billing line entry."""

    head: str
    amount: int = Field(gt=0, description="Amount in paise")


class ClaimSubmitRequest(BaseModel):
    """Reimbursement or cashless final claim submission payload."""

    client_reference: str | None = None
    policy_number: str
    member_name: str
    acting_user: str | None = None
    claim_type: str = Field(default="reimbursement")
    admission_date: str
    discharge_date: str
    claimed_amount: int = Field(gt=0, description="Total in paise")
    line_items: list[LineItem] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class QueryRaiseRequest(BaseModel):
    """Operator payload to issue a communication request (query)."""

    items: list[dict[str, str]] = Field(description="List of deficiency items with code, label, description")
    due_days: int = Field(default=15, ge=1)
    inject_malicious: bool = False


class AnswerQueryRequest(BaseModel):
    """Payload providing response documents to resolve an open query."""

    documents: list[dict[str, Any]] = Field(description="List of newly submitted documents")


class DecideClaimRequest(BaseModel):
    """Operator payload to adjudicate a claim."""

    outcome: str = Field(description="approved, partially_approved, or rejected")
    rejection_reason: str | None = None
    policy_clause: str | None = None
    line_decisions: list[dict[str, Any]] | None = None


class PayClaimRequest(BaseModel):
    """Operator payload to advise payment and post credit."""

    payee: str = Field(default="member", description="member or hospital")
    bank_account_last4: str = "8921"
    credit_amount_override: int | None = None
    credit_delay_days: int = 0
    utr_override: str | None = None
    skip_credit: bool = False


# Endpoints
@router.get("/policies/{policy_number}")
def get_policy(policy_number: str) -> dict:
    """Retrieve policy details and available limits. Returns 404 if not found."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM policies WHERE policy_number = ?;", (policy_number,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": {"code": "POLICY_NOT_FOUND", "message": f"Policy {policy_number} not found", "retryable": False}})
        d = row_to_dict(row)
        d["mock"] = True
        return d
    finally:
        conn.close()


@router.post("/eligibility")
def check_eligibility(req: EligibilityRequest) -> dict:
    """Check whether a policyholder/member is eligible for treatment coverage."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM policies WHERE policy_number = ?;", (req.policy_number,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": {"code": "POLICY_NOT_FOUND", "message": f"Policy {req.policy_number} not found", "retryable": False}})
        policy = row_to_dict(row)

        reasons = []
        # Check dates
        if not (policy["period_start"] <= req.treatment_date <= policy["period_end"]):
            reasons.append(f"Treatment date {req.treatment_date} is outside policy period ({policy['period_start']} to {policy['period_end']})")

        # Check member
        members = policy.get("members", [])
        member_match = next((m for m in members if m.get("name", "").lower() == req.member_name.lower()), None)
        if not member_match:
            reasons.append(f"Member '{req.member_name}' is not listed on this policy")

        is_eligible = len(reasons) == 0
        return {
            "eligible": is_eligible,
            "reasons": reasons,
            "balance_sum_insured": policy["balance_sum_insured"],
            "mock": True
        }
    finally:
        conn.close()


@router.post("/preauths")
def submit_preauth(req: PreauthRequest, api_key: str = Depends(verify_api_key)) -> dict:
    """Hospital cashless desk submits a pre-authorisation request."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM policies WHERE policy_number = ?;", (req.policy_number,))
        p_row = cur.fetchone()
        if not p_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "POLICY_NOT_FOUND", "message": f"Policy {req.policy_number} not found", "retryable": False}})
        policy = row_to_dict(p_row)

        member = next((m for m in policy.get("members", []) if m.get("name", "").lower() == req.member_name.lower()), None)
        if not member:
            raise HTTPException(status_code=422, detail={"error": {"code": "MEMBER_NOT_COVERED", "message": f"Member {req.member_name} not covered", "retryable": False}})

        preauth_id = f"PA-{uuid.uuid4().hex[:8].upper()}"
        now = get_current_time_iso(conn)

        # Basic preauth approval logic
        approved_amt = min(req.estimated_amount, policy["balance_sum_insured"])
        status = "approved" if approved_amt > 0 else "rejected"

        conn.execute("""
        INSERT INTO preauths (id, policy_id, member_id, hospital_id, admission_date, diagnosis_text, estimated_amount, status, approved_amount, conditions, version, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', 1, ?);
        """, (
            preauth_id, policy["id"], member["member_id"], req.hospital_id,
            req.admission_date, req.diagnosis_text, req.estimated_amount,
            status, approved_amt, now
        ))
        conn.commit()

        record_and_dispatch_event("preauth.submitted", "preauth", preauth_id, 1, {"preauth_id": preauth_id, "status": status}, conn)

        return {
            "id": preauth_id,
            "policy_id": policy["id"],
            "status": status,
            "approved_amount": approved_amt,
            "version": 1,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/claims")
async def submit_claim(
    request: Request,
    req: ClaimSubmitRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    api_key: str = Depends(verify_api_key)
) -> dict:
    """Submit a reimbursement or cashless final claim with idempotency support."""
    conn = get_connection()
    try:
        raw_body = await request.body()
        endpoint = "/payer/claims"

        if idempotency_key:
            cached = check_idempotency(conn, idempotency_key, endpoint, raw_body)
            if cached:
                return cached["body"]

        cur = conn.cursor()
        cur.execute("SELECT * FROM policies WHERE policy_number = ?;", (req.policy_number,))
        p_row = cur.fetchone()
        if not p_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "POLICY_NOT_FOUND", "message": f"Policy {req.policy_number} not found", "retryable": False}})
        policy = row_to_dict(p_row)

        # Check member
        member = next((m for m in policy.get("members", []) if m.get("name", "").lower() == req.member_name.lower()), None)
        if not member:
            raise HTTPException(status_code=422, detail={"error": {"code": "MEMBER_NOT_COVERED", "message": f"Member {req.member_name} not covered", "retryable": False}})

        # Check authorization if acting on behalf
        if req.acting_user and req.acting_user.lower() != req.member_name.lower():
            reps = policy.get("authorised_representatives", [])
            auth_rep = next((r for r in reps if r.get("name", "").lower() == req.acting_user.lower()), None)
            if not auth_rep or auth_rep.get("status") != "active":
                raise HTTPException(status_code=403, detail={"error": {"code": "NOT_AUTHORISED_REPRESENTATIVE", "message": f"User {req.acting_user} is not an active authorized representative", "retryable": False}})

        claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
        now = get_current_time_iso(conn)

        line_items_data = [item.model_dump() for item in req.line_items]

        conn.execute("""
        INSERT INTO claims (
            id, client_reference, policy_id, member_id, claim_type, admission_date,
            discharge_date, claimed_amount, line_items, documents, submitted_at,
            status, version, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', 1, ?);
        """, (
            claim_id, req.client_reference, policy["id"], member["member_id"],
            req.claim_type, req.admission_date, req.discharge_date,
            req.claimed_amount, json.dumps(line_items_data), json.dumps(req.documents),
            now, now
        ))
        conn.commit()

        res_body = {
            "id": claim_id,
            "client_reference": req.client_reference,
            "policy_id": policy["id"],
            "status": "submitted",
            "claimed_amount": req.claimed_amount,
            "version": 1,
            "submitted_at": now,
            "mock": True
        }

        if idempotency_key:
            record_idempotency(conn, idempotency_key, endpoint, raw_body, 201, res_body, now)

        record_and_dispatch_event("claim.submitted", "claim", claim_id, 1, res_body, conn)

        # Check drop response fault
        check_and_apply_drop_fault(conn)

        return res_body
    finally:
        conn.close()


@router.get("/claims")
def list_claims(client_reference: str | None = Query(default=None)) -> list[dict]:
    """Search claims by client_reference for lost response recovery."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if client_reference:
            cur.execute("SELECT * FROM claims WHERE client_reference = ?;", (client_reference,))
        else:
            cur.execute("SELECT * FROM claims ORDER BY rowid DESC LIMIT 20;")
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = row_to_dict(r)
            d["mock"] = True
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str) -> dict:
    """Retrieve full claim details including queries, decision, and payment."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        # Fetch queries
        cur.execute("SELECT * FROM queries WHERE claim_id = ? ORDER BY rowid ASC;", (claim_id,))
        claim["queries"] = [row_to_dict(q) for q in cur.fetchall()]

        # Fetch decision
        cur.execute("SELECT * FROM decisions WHERE claim_id = ?;", (claim_id,))
        d_row = cur.fetchone()
        claim["decision"] = row_to_dict(d_row)

        # Fetch payments
        cur.execute("SELECT * FROM payments WHERE claim_id = ?;", (claim_id,))
        claim["payments"] = [row_to_dict(p) for p in cur.fetchall()]

        claim["mock"] = True
        return claim
    finally:
        conn.close()


@router.post("/claims/{claim_id}/query")
def raise_claim_query(claim_id: str, req: QueryRaiseRequest) -> dict:
    """Operator action: Raise a deficiency query letter on a submitted claim."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        if claim["status"] not in ("submitted", "under_review"):
            raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": f"Cannot raise query in status '{claim['status']}'", "retryable": False}})

        query_id = f"QRY-{uuid.uuid4().hex[:8].upper()}"
        now = get_current_time_iso(conn)

        # Compute due date
        from datetime import datetime, timedelta
        due_dt = datetime.fromisoformat(now) + timedelta(days=req.due_days)
        due_at = due_dt.isoformat()

        conn.execute("""
        INSERT INTO queries (id, claim_id, raised_at, due_at, items, status)
        VALUES (?, ?, ?, ?, ?, 'open');
        """, (query_id, claim_id, now, due_at, json.dumps(req.items)))

        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = 'query_raised', version = ?, updated_at = ? WHERE id = ?;", (new_version, now, claim_id))
        conn.commit()

        # Generate query letter PDF
        query_dict = {"id": query_id, "raised_at": now, "due_at": due_at, "items": req.items}
        doc_id = f"DOC-QRY-{query_id}"
        generate_query_letter_pdf(doc_id, claim, query_dict, req.inject_malicious)

        record_and_dispatch_event("claim.query_raised", "claim", claim_id, new_version, {"claim_id": claim_id, "query_id": query_id}, conn)

        return {"query_id": query_id, "status": "query_raised", "due_at": due_at, "letter_doc_id": doc_id, "mock": True}
    finally:
        conn.close()


@router.post("/claims/{claim_id}/documents")
def answer_claim_query(claim_id: str, req: AnswerQueryRequest) -> dict:
    """Member responds to an open deficiency query with documents."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        if claim["status"] != "query_raised":
            raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": "Claim is not in query_raised status", "retryable": False}})

        now = get_current_time_iso(conn)

        # Mark open query answered
        cur.execute("UPDATE queries SET status = 'answered', answered_at = ? WHERE claim_id = ? AND status = 'open';", (now, claim_id))

        # Append documents
        existing_docs = claim.get("documents", [])
        existing_docs.extend(req.documents)

        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = 'under_review', documents = ?, version = ?, updated_at = ? WHERE id = ?;", (json.dumps(existing_docs), new_version, now, claim_id))
        conn.commit()

        record_and_dispatch_event("claim.query_answered", "claim", claim_id, new_version, {"claim_id": claim_id}, conn)

        return {"claim_id": claim_id, "status": "under_review", "version": new_version, "mock": True}
    finally:
        conn.close()


@router.post("/claims/{claim_id}/decide")
def decide_claim(claim_id: str, req: DecideClaimRequest) -> dict:
    """Operator action: Adjudicate claim and apply deterministic deduction arithmetic."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        if claim["status"] not in ("submitted", "under_review", "reopened"):
            raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": f"Cannot decide claim in status '{claim['status']}'", "retryable": False}})

        # Load policy
        cur.execute("SELECT * FROM policies WHERE id = ?;", (claim["policy_id"],))
        policy = row_to_dict(cur.fetchone())

        now = get_current_time_iso(conn)
        decision_id = f"DEC-{uuid.uuid4().hex[:8].upper()}"

        line_items = claim.get("line_items", [])
        approved_amt = 0
        line_decisions = req.line_decisions or []

        if req.outcome == "rejected":
            validate_decision_clauses("rejected", [], req.rejection_reason, req.policy_clause)
            approved_amt = 0
        else:
            # If line_decisions not explicitly provided, calculate deterministically
            if not line_decisions:
                approved_amt, line_decisions, clauses = calculate_line_decisions(
                    line_items=line_items,
                    room_rent_limit_per_day=policy.get("room_rent_limit_per_day", 500000),
                    days_admitted=3,
                    sub_limits=policy.get("sub_limits", []),
                    copay_percent=policy.get("copay_percent", 0),
                    deductible=policy.get("deductible", 0),
                    balance_sum_insured=policy.get("balance_sum_insured", 50000000)
                )
            else:
                approved_amt = sum(ld.get("approved", 0) for ld in line_decisions)
                validate_decision_clauses(req.outcome, line_decisions, None, None)

        conn.execute("""
        INSERT OR REPLACE INTO decisions (
            id, claim_id, outcome, decided_at, approved_amount, line_decisions,
            rejection_reason, policy_clause, letter_doc_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            decision_id, claim_id, req.outcome, now, approved_amt,
            json.dumps(line_decisions), req.rejection_reason, req.policy_clause, f"DOC-DEC-{decision_id}"
        ))

        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = ?, version = ?, updated_at = ? WHERE id = ?;", (req.outcome, new_version, now, claim_id))
        conn.commit()

        # Generate decision letter PDF
        dec_dict = {
            "id": decision_id, "outcome": req.outcome, "decided_at": now,
            "approved_amount": approved_amt, "line_decisions": line_decisions,
            "rejection_reason": req.rejection_reason, "policy_clause": req.policy_clause
        }
        generate_decision_letter_pdf(f"DOC-DEC-{decision_id}", claim, dec_dict)

        record_and_dispatch_event("claim.decided", "claim", claim_id, new_version, dec_dict, conn)

        return {
            "decision_id": decision_id,
            "status": req.outcome,
            "approved_amount": approved_amt,
            "line_decisions": line_decisions,
            "letter_doc_id": f"DOC-DEC-{decision_id}",
            "mock": True
        }
    finally:
        conn.close()


@router.post("/claims/{claim_id}/pay")
def pay_claim(claim_id: str, req: PayClaimRequest) -> dict:
    """Operator action: Advise settlement payment and record bank credit."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        if claim["status"] not in ("approved", "partially_approved"):
            raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": f"Cannot pay claim in status '{claim['status']}'", "retryable": False}})

        # Fetch approved amount from decision
        cur.execute("SELECT * FROM decisions WHERE claim_id = ?;", (claim_id,))
        d_row = cur.fetchone()
        if not d_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "DECISION_MISSING", "message": "Decision not found for claim", "retryable": False}})
        decision = row_to_dict(d_row)

        advised_amount = decision["approved_amount"]
        payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        utr = req.utr_override or f"UTR-{uuid.uuid4().hex[:12].upper()}"
        now = get_current_time_iso(conn)

        conn.execute("""
        INSERT INTO payments (id, claim_id, amount, utr, paid_at, payee, bank_account_last4)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (payment_id, claim_id, advised_amount, utr, now, req.payee, req.bank_account_last4))

        # Update balance_sum_insured
        conn.execute("""
        UPDATE policies SET balance_sum_insured = MAX(0, balance_sum_insured - ?) WHERE id = ?;
        """, (advised_amount, claim["policy_id"]))

        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = 'payment_advised', version = ?, updated_at = ? WHERE id = ?;", (new_version, now, claim_id))

        # Automatically credit bank if not skipped
        credit_id = None
        if not req.skip_credit and req.payee == "member":
            credit_amount = req.credit_amount_override if req.credit_amount_override is not None else advised_amount
            credit_id = f"CR-{uuid.uuid4().hex[:8].upper()}"
            conn.execute("""
            INSERT INTO bank_credits (id, account_id, amount, utr, credited_at, narration)
            VALUES (?, 'ACC-001', ?, ?, ?, ?);
            """, (credit_id, credit_amount, utr, now, f"CMS/SURAKSHA/{claim_id}"))

        conn.commit()

        record_and_dispatch_event("payment.advised", "claim", claim_id, new_version, {
            "claim_id": claim_id,
            "payment_id": payment_id,
            "amount": advised_amount,
            "utr": utr,
            "credit_id": credit_id
        }, conn)

        return {
            "payment_id": payment_id,
            "status": "payment_advised",
            "amount": advised_amount,
            "utr": utr,
            "credit_id": credit_id,
            "mock": True
        }
    finally:
        conn.close()


@router.post("/claims/{claim_id}/reopen")
def reopen_claim(claim_id: str) -> dict:
    """Operator action: Reopen a rejected or partially approved claim."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        if claim["status"] not in ("rejected", "partially_approved", "payment_advised"):
            raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": f"Cannot reopen claim in status '{claim['status']}'", "retryable": False}})

        now = get_current_time_iso(conn)
        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = 'reopened', version = ?, updated_at = ? WHERE id = ?;", (new_version, now, claim_id))
        conn.commit()

        record_and_dispatch_event("claim.reopened", "claim", claim_id, new_version, {"claim_id": claim_id}, conn)

        return {"claim_id": claim_id, "status": "reopened", "version": new_version, "mock": True}
    finally:
        conn.close()


@router.post("/claims/{claim_id}/withdraw")
def withdraw_claim(claim_id: str) -> dict:
    """Member withdraws an open claim."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,))
        c_row = cur.fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found", "retryable": False}})
        claim = row_to_dict(c_row)

        now = get_current_time_iso(conn)
        new_version = claim["version"] + 1
        conn.execute("UPDATE claims SET status = 'withdrawn', version = ?, updated_at = ? WHERE id = ?;", (new_version, now, claim_id))
        conn.commit()

        return {"claim_id": claim_id, "status": "withdrawn", "version": new_version, "mock": True}
    finally:
        conn.close()


@router.get("/documents/{doc_id}.pdf")
def download_payer_document_pdf(doc_id: str):
    """Download a generated insurer letter or policy schedule PDF."""
    file_path = os.path.join(ensure_storage_dir(), f"{doc_id}.pdf")
    if not os.path.exists(file_path) and doc_id.startswith("DOC-POL-"):
        pol_num = doc_id.replace("DOC-POL-", "", 1)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM policies WHERE policy_number = ? OR id = ?;", (pol_num, pol_num))
            row = cur.fetchone()
            if row:
                file_path = generate_policy_pdf(doc_id, row_to_dict(row))
        finally:
            conn.close()
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Payer document PDF not found on disk")
    return FileResponse(file_path, media_type="application/pdf", filename=f"{doc_id}.pdf")
