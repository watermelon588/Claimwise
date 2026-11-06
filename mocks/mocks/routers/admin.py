"""Admin and scenario management endpoints."""

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from mocks.clock import get_current_time_iso
from mocks.db import get_connection, row_to_dict
from mocks.faults import get_faults
from mocks.services.scenarios import reset_database, load_scenario

router = APIRouter(prefix="/admin", tags=["Admin Operations"])

SCENARIOS_CATALOG = [
    {"name": "standard_reimbursement", "description": "Retail individual policy, discharge done, claim approved in full, credit matches."},
    {"name": "cashless_partial", "description": "Family floater, pre-auth partially approved (room rent over limit), final bill, partial payment to hospital."},
    {"name": "repeated_renamed_request", "description": "Query asks for 'Discharge summary', answered, then a second query asks for 'Discharge card'."},
    {"name": "partial_with_mismatched_credit", "description": "Partial approval Rs 42,300; bank credit Rs 38,300 with a different UTR narration."},
    {"name": "rejection_to_ombudsman", "description": "Rejection citing non-disclosure; grievance resolved against member; ombudsman eligible."},
    {"name": "silent_insurer", "description": "Claim submitted, no action; clock can jump past the 15-day settlement TAT."},
    {"name": "caregiver_consent_change_two_policies", "description": "Adult child authorised representative status changes to revoked; patient also has a group policy."},
    {"name": "lost_submit_response", "description": "Fault injection on: next claim submit is stored but the HTTP response is dropped."},
    {"name": "malicious_document_text", "description": "A generated query letter contains injected instructions to test that Claimwise treats text as data."}
]


class ResetResponse(BaseModel):
    """Response returned upon clearing and reseeding database."""

    status: str
    message: str
    mock: bool = True


@router.get("/overview")
def get_admin_overview() -> dict:
    """Return a unified snapshot of all mock services, entities, clock, faults, scenarios, and events."""
    conn = get_connection()
    try:
        cur = conn.cursor()

        def fetch_all(table: str, order: str = "rowid DESC") -> list[dict]:
            """Every row of one mock table (fixed table names from this function only, never user input)."""
            cur.execute(f"SELECT * FROM {table} ORDER BY {order};")
            return [row_to_dict(r) for r in cur.fetchall() if r is not None]

        claims = fetch_all("claims")
        for c in claims:
            cid = c["id"]
            cur.execute("SELECT * FROM queries WHERE claim_id = ? ORDER BY rowid ASC;", (cid,))
            c["queries"] = [row_to_dict(q) for q in cur.fetchall()]
            cur.execute("SELECT * FROM decisions WHERE claim_id = ?;", (cid,))
            c["decision"] = row_to_dict(cur.fetchone())
            cur.execute("SELECT * FROM payments WHERE claim_id = ? ORDER BY rowid ASC;", (cid,))
            c["payments"] = [row_to_dict(p) for p in cur.fetchall()]

        raw_events = fetch_all("events", "rowid DESC")
        events = []
        for e in raw_events:
            payload = e.get("payload")
            events.append({
                "event_id": e["id"],
                "event_type": e["event_type"],
                "occurred_at": e["occurred_at"],
                "resource": {
                    "type": e["resource_type"],
                    "id": e["resource_id"],
                    "version": e["resource_version"],
                },
                "data": payload if isinstance(payload, dict) else {},
                "delivery_attempts": e.get("delivery_attempts", 0),
                "status": e.get("status", "pending"),
                "mock": True,
            })

        return {
            "clock": {"current_time": get_current_time_iso(conn), "mock": True},
            "faults": get_faults(conn).model_dump(),
            "scenarios": SCENARIOS_CATALOG,
            "policies": fetch_all("policies", "id ASC"),
            "preauths": fetch_all("preauths"),
            "claims": claims,
            "hospitals": fetch_all("hospitals", "id ASC"),
            "admissions": fetch_all("admissions"),
            "hospital_documents": fetch_all("hospital_documents"),
            "bank_accounts": fetch_all("bank_accounts", "id ASC"),
            "bank_credits": fetch_all("bank_credits", "credited_at DESC"),
            "grievances": fetch_all("grievances"),
            "ombudsman_complaints": fetch_all("ombudsman_complaints"),
            "events": events,
            "mock": True,
        }
    finally:
        conn.close()


@router.post("/reset", response_model=ResetResponse)
def reset_endpoint() -> ResetResponse:
    """Reset the mock database and re-initialize baseline entities."""
    reset_database()
    return ResetResponse(
        status="success",
        message="Database reset and reseeded with base entities."
    )


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    """List all available pre-configured test scenarios."""
    return SCENARIOS_CATALOG


@router.post("/scenarios/{name}")
def trigger_scenario(name: str) -> dict:
    """Reset database and apply the selected test scenario."""
    valid_names = {s["name"] for s in SCENARIOS_CATALOG}
    if name not in valid_names:
        raise HTTPException(status_code=404, detail=f"Scenario '{name}' not found. Valid: {list(valid_names)}")
    res = load_scenario(name)
    res["mock"] = True
    return res
