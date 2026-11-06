"""Virtual clock implementation for deterministic mock deadlines and timers."""

from datetime import datetime, timedelta, timezone
import sqlite3
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from mocks.db import get_connection

tz_in = timezone(timedelta(hours=5, minutes=30))
router = APIRouter(prefix="/admin/clock", tags=["Admin Clock"])



class ClockResponse(BaseModel):
    """Response model for virtual clock endpoints."""

    current_time: str
    mock: bool = True


class ClockAdvanceRequest(BaseModel):
    """Request payload to advance the virtual clock."""

    days: int = Field(default=0, ge=0)
    hours: int = Field(default=0, ge=0)
    minutes: int = Field(default=0, ge=0)


class ClockSetRequest(BaseModel):
    """Request payload to set the virtual clock directly."""

    at: str


def get_current_time(conn: sqlite3.Connection | None = None) -> datetime:
    """Return current virtual clock as a timezone-aware datetime object."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT virtual_time FROM clock WHERE id = 1;")
        row = cur.fetchone()
        if not row:
            return datetime(2026, 10, 1, 10, 0, tzinfo=tz_in)
        return datetime.fromisoformat(row["virtual_time"])
    finally:
        if close_after:
            conn.close()


def get_current_time_iso(conn: sqlite3.Connection | None = None) -> str:
    """Return current virtual clock as ISO 8601 string with +05:30 offset."""
    dt = get_current_time(conn)
    return dt.isoformat()


def advance_time(days: int = 0, hours: int = 0, minutes: int = 0, conn: sqlite3.Connection | None = None) -> str:
    """Advance the virtual clock by specified delta and persist to database."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        current = get_current_time(conn)
        new_dt = current + timedelta(days=days, hours=hours, minutes=minutes)
        new_iso = new_dt.isoformat()
        conn.execute("UPDATE clock SET virtual_time = ? WHERE id = 1;", (new_iso,))
        conn.commit()
        return new_iso
    finally:
        if close_after:
            conn.close()


def set_time(at_iso: str, conn: sqlite3.Connection | None = None) -> str:
    """Explicitly set the virtual clock to a specified ISO 8601 string."""
    try:
        dt = datetime.fromisoformat(at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_in)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ISO 8601 timestamp: {e}")

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        iso_str = dt.isoformat()
        conn.execute("UPDATE clock SET virtual_time = ? WHERE id = 1;", (iso_str,))
        conn.commit()
        return iso_str
    finally:
        if close_after:
            conn.close()


@router.get("", response_model=ClockResponse)
def get_clock() -> ClockResponse:
    """Get the current virtual clock timestamp."""
    return ClockResponse(current_time=get_current_time_iso())


@router.post("/advance", response_model=ClockResponse)
def advance_clock(req: ClockAdvanceRequest) -> ClockResponse:
    """Advance the virtual clock by a number of days, hours, and minutes."""
    new_time = advance_time(days=req.days, hours=req.hours, minutes=req.minutes)
    return ClockResponse(current_time=new_time)


@router.post("/set", response_model=ClockResponse)
def set_clock_endpoint(req: ClockSetRequest) -> ClockResponse:
    """Set the virtual clock to a specific ISO 8601 timestamp."""
    new_time = set_time(req.at)
    return ClockResponse(current_time=new_time)
