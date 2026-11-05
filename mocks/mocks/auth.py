"""Authentication and idempotency helpers for mock endpoints."""

import hashlib
import json
import sqlite3
from typing import Callable, Any
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from mocks.config import settings
from mocks.db import get_connection
from mocks.faults import get_faults

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Validate incoming X-Api-Key against allowed participant keys."""
    if not api_key or api_key not in settings.api_keys_list:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORISED", "message": "Missing or invalid X-Api-Key header", "retryable": False}}
        )
    return api_key


def check_idempotency(
    conn: sqlite3.Connection,
    key: str,
    endpoint: str,
    request_body_bytes: bytes,
) -> dict[str, Any] | None:
    """Check if an idempotency key was previously processed."""
    request_hash = hashlib.sha256(request_body_bytes).hexdigest()
    cur = conn.cursor()
    cur.execute("SELECT request_hash, status_code, response_body FROM idempotency WHERE key = ? AND endpoint = ?;", (key, endpoint))
    row = cur.fetchone()
    if row:
        stored_hash = row["request_hash"]
        if stored_hash != request_hash:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "IDEMPOTENCY_CONFLICT", "message": "Same idempotency key used with different payload", "retryable": False}}
            )
        try:
            body = json.loads(row["response_body"])
        except Exception:
            body = row["response_body"]
        return {"status_code": row["status_code"], "body": body}
    return None


def record_idempotency(
    conn: sqlite3.Connection,
    key: str,
    endpoint: str,
    request_body_bytes: bytes,
    status_code: int,
    response_body: Any,
    created_at_iso: str,
) -> None:
    """Store the completed response for an idempotency key."""
    request_hash = hashlib.sha256(request_body_bytes).hexdigest()
    body_str = json.dumps(response_body) if not isinstance(response_body, str) else response_body
    conn.execute("""
    INSERT OR REPLACE INTO idempotency (key, endpoint, request_hash, status_code, response_body, created_at)
    VALUES (?, ?, ?, ?, ?, ?);
    """, (key, endpoint, request_hash, status_code, body_str, created_at_iso))
    conn.commit()


def check_and_apply_drop_fault(conn: sqlite3.Connection) -> None:
    """If drop_response_after_commit fault is active, raise 500 after commit."""
    faults = get_faults(conn)
    if faults.drop_response_after_commit:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "INTERNAL", "message": "Connection dropped after commit (simulated fault)", "retryable": True}}
        )
