"""Bank service router for patient account statements and credit reconciliation."""

import os
import sqlite3
import uuid
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from mocks.auth import verify_api_key
from mocks.clock import get_current_time_iso
from mocks.db import get_connection, row_to_dict
from mocks.events import record_and_dispatch_event
from mocks.services.pdf_generator import generate_bank_statement_pdf

router = APIRouter(prefix="/bank", tags=["Bank Service (M3)"])


class PostCreditRequest(BaseModel):
    """Payload to post an inbound settlement credit to a patient's account."""

    amount: int = Field(gt=0, description="Amount in paise")
    utr: str
    narration: str = "NEFT / SETTLEMENT CREDIT"
    credited_at: str | None = None


@router.post("/accounts/{account_id}/credits")
def post_credit(account_id: str, req: PostCreditRequest, api_key: str = Depends(verify_api_key)) -> dict:
    """Record an inbound bank credit on an account."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM bank_accounts WHERE id = ?;", (account_id,))
        a_row = cur.fetchone()
        if not a_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "ACCOUNT_NOT_FOUND", "message": f"Bank account {account_id} not found", "retryable": False}})

        credit_id = f"CR-{uuid.uuid4().hex[:8].upper()}"
        now = req.credited_at or get_current_time_iso(conn)

        conn.execute("""
        INSERT INTO bank_credits (id, account_id, amount, utr, credited_at, narration)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (credit_id, account_id, req.amount, req.utr, now, req.narration))
        conn.commit()

        record_and_dispatch_event("bank.credit_posted", "bank_account", account_id, 1, {
            "account_id": account_id,
            "credit_id": credit_id,
            "amount": req.amount,
            "utr": req.utr
        }, conn)

        return {
            "credit_id": credit_id,
            "account_id": account_id,
            "amount": req.amount,
            "utr": req.utr,
            "credited_at": now,
            "mock": True
        }
    finally:
        conn.close()


@router.get("/accounts/{account_id}/statement")
def get_statement_json(account_id: str) -> dict:
    """Fetch statement credits for an account in JSON format."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM bank_accounts WHERE id = ?;", (account_id,))
        a_row = cur.fetchone()
        if not a_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "ACCOUNT_NOT_FOUND", "message": f"Bank account {account_id} not found", "retryable": False}})
        account = row_to_dict(a_row)

        cur.execute("SELECT * FROM bank_credits WHERE account_id = ? ORDER BY credited_at ASC;", (account_id,))
        credits = [row_to_dict(c) for c in cur.fetchall()]

        return {
            "account": account,
            "credits": credits,
            "total_credits": sum(c.get("amount", 0) for c in credits),
            "mock": True
        }
    finally:
        conn.close()


@router.get("/accounts/{account_id}/statement.pdf")
def get_statement_pdf(account_id: str):
    """Generate and return the bank statement PDF."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM bank_accounts WHERE id = ?;", (account_id,))
        a_row = cur.fetchone()
        if not a_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "ACCOUNT_NOT_FOUND", "message": f"Bank account {account_id} not found", "retryable": False}})
        account = row_to_dict(a_row)

        cur.execute("SELECT * FROM bank_credits WHERE account_id = ? ORDER BY credited_at ASC;", (account_id,))
        credits = [row_to_dict(c) for c in cur.fetchall()]

        doc_id = f"DOC-STMT-{account_id}"
        pdf_path = generate_bank_statement_pdf(doc_id, account, credits)

        return FileResponse(pdf_path, media_type="application/pdf", filename=f"statement_{account_id}.pdf")
    finally:
        conn.close()
