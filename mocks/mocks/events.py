"""Event dispatcher and webhook delivery with HMAC SHA-256 signatures."""

import hashlib
import hmac
import json
import sqlite3
import uuid
import httpx
from pydantic import BaseModel, Field
from fastapi import APIRouter, Query
from mocks.config import settings
from mocks.clock import get_current_time_iso
from mocks.db import get_connection, row_to_dict
from mocks.faults import get_faults

router = APIRouter(prefix="/events", tags=["Events & Webhooks"])


class EventResource(BaseModel):
    """Resource reference inside an event notification."""

    type: str
    id: str
    version: int = 1


class EventItem(BaseModel):
    """Published event record."""

    event_id: str
    event_type: str
    occurred_at: str
    resource: EventResource
    data: dict
    mock: bool = True


def generate_event_id() -> str:
    """Generate a unique sequential-style event identifier."""
    return f"EVT-{uuid.uuid4().hex[:12].upper()}"


def compute_hmac_signature(raw_body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature over raw payload."""
    sig = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def record_and_dispatch_event(
    event_type: str,
    resource_type: str,
    resource_id: str,
    resource_version: int,
    data: dict,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Record event in database and queue/dispatch webhook to Claimwise."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    event_id = generate_event_id()
    occurred_at = get_current_time_iso(conn)

    try:
        conn.execute("""
        INSERT INTO events (id, event_type, occurred_at, resource_type, resource_id, resource_version, payload, delivery_attempts, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending');
        """, (
            event_id,
            event_type,
            occurred_at,
            resource_type,
            resource_id,
            resource_version,
            json.dumps(data),
        ))
        conn.commit()

        # Check faults for webhook down
        faults = get_faults(conn)
        if not faults.webhook_down:
            dispatch_webhook_async(event_id, event_type, occurred_at, resource_type, resource_id, resource_version, data, faults.duplicate_webhooks)

        return event_id
    finally:
        if close_after:
            conn.close()


def dispatch_webhook_async(
    event_id: str,
    event_type: str,
    occurred_at: str,
    resource_type: str,
    resource_id: str,
    resource_version: int,
    data: dict,
    duplicate: bool = False,
) -> None:
    """Fire webhook HTTP POST asynchronously in fire-and-forget mode."""
    payload_obj = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "resource": {
            "type": resource_type,
            "id": resource_id,
            "version": resource_version
        },
        "data": data,
        "mock": True
    }
    raw_json = json.dumps(payload_obj)
    signature = compute_hmac_signature(raw_json, settings.mock_webhook_secret)

    headers = {
        "Content-Type": "application/json",
        "X-Mock-Signature": signature
    }

    try:
        # Fire with short timeout so caller does not block if listener is offline
        with httpx.Client(timeout=1.0) as client:
            client.post(settings.claimwise_webhook_url, content=raw_json, headers=headers)
            if duplicate:
                client.post(settings.claimwise_webhook_url, content=raw_json, headers=headers)
    except Exception:
        # If recipient is offline during mock tests, event remains in events table for polling
        pass


@router.get("", response_model=list[dict])
def list_events(after: str | None = Query(default=None, description="Event ID to fetch events after")) -> list[dict]:
    """Poll recorded events in chronological order, optionally starting after an event ID."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if after:
            cur.execute("""
            SELECT * FROM events
            WHERE rowid > (SELECT COALESCE(MAX(rowid), 0) FROM events WHERE id = ?)
            ORDER BY rowid ASC;
            """, (after,))
        else:
            cur.execute("SELECT * FROM events ORDER BY rowid ASC;")

        rows = cur.fetchall()
        result = []
        for r in rows:
            d = row_to_dict(r)
            payload = d.get("payload")
            result.append({
                "event_id": d["id"],
                "event_type": d["event_type"],
                "occurred_at": d["occurred_at"],
                "resource": {
                    "type": d["resource_type"],
                    "id": d["resource_id"],
                    "version": d["resource_version"]
                },
                "data": payload if isinstance(payload, dict) else {},
                "delivery_attempts": d.get("delivery_attempts", 0),
                "status": d.get("status", "pending"),
                "mock": True
            })
        return result
    finally:
        conn.close()
