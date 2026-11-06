"""Fault injection settings and execution helpers for testing edge cases."""

import asyncio
import random
import sqlite3
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from mocks.db import get_connection

router = APIRouter(prefix="/admin/faults", tags=["Admin Faults"])


class FaultsModel(BaseModel):
    """Configuration model for mock fault injection."""

    drop_response_after_commit: bool = False
    delay_ms: int = Field(default=0, ge=0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    duplicate_webhooks: bool = False
    webhook_down: bool = False
    mock: bool = True


def get_faults(conn: sqlite3.Connection | None = None) -> FaultsModel:
    """Fetch current fault injection configuration from database."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM faults WHERE id = 1;")
        row = cur.fetchone()
        if not row:
            return FaultsModel()
        return FaultsModel(
            drop_response_after_commit=bool(row["drop_response_after_commit"]),
            delay_ms=int(row["delay_ms"]),
            error_rate=float(row["error_rate"]),
            duplicate_webhooks=bool(row["duplicate_webhooks"]),
            webhook_down=bool(row["webhook_down"]),
        )
    finally:
        if close_after:
            conn.close()


def set_faults(faults: FaultsModel, conn: sqlite3.Connection | None = None) -> FaultsModel:
    """Update active fault injection settings."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        conn.execute("""
        UPDATE faults SET
            drop_response_after_commit = ?,
            delay_ms = ?,
            error_rate = ?,
            duplicate_webhooks = ?,
            webhook_down = ?
        WHERE id = 1;
        """, (
            1 if faults.drop_response_after_commit else 0,
            faults.delay_ms,
            faults.error_rate,
            1 if faults.duplicate_webhooks else 0,
            1 if faults.webhook_down else 0,
        ))
        conn.commit()
        return faults
    finally:
        if close_after:
            conn.close()


async def apply_ingress_faults(conn: sqlite3.Connection | None = None) -> None:
    """Apply latency delay or random simulated errors according to active fault configuration."""
    faults = get_faults(conn)
    if faults.delay_ms > 0:
        await asyncio.sleep(faults.delay_ms / 1000.0)

    if faults.error_rate > 0.0 and random.random() < faults.error_rate:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "INTERNAL", "message": "Simulated fault injected", "retryable": True}}
        )


@router.get("", response_model=FaultsModel)
def get_faults_endpoint() -> FaultsModel:
    """Retrieve current fault injection settings."""
    return get_faults()


@router.post("", response_model=FaultsModel)
def update_faults_endpoint(req: FaultsModel) -> FaultsModel:
    """Set or update fault injection configuration."""
    return set_faults(req)
