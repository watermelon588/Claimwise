"""Submission (DEV-021): send the approved pack through the connected account, or record a manual submission.

Pure Python around the connector client. Safety rules:
- Only the exact approved pack (by hash) is ever sent.
- The client reference doubles as the idempotency key, so a retry can never create a second claim.
- Before every send, and after any unclear failure, the payer is asked whether it already has the claim
  (the "accepted but the answer was lost" case).
"""

import hashlib
from datetime import date, datetime, timedelta

from app import connector
from app.agent.authority import acting_user, authority_issues
from app.agent.claim import _latest_facts, build_submission_pack
from app.agent.prompts import (
    ALREADY_SUBMITTED_REPLY, BAD_DATE_REPLY, MANUAL_RECORDED_REPLY, NEED_APPROVAL_REPLY, NEED_CONNECTION_REPLY,
    NOTE_CONNECTION_EXPIRED, NOTE_SUBMITTED, PACK_INCOMPLETE_REPLY, REFUSAL_REASONS, REFUSED_REPLY, SUBMITTED_REPLY,
    UNCONFIRMED_REPLY,
)
from app.agent.state import AgentState
from app.agent.tools import RULES

SETTLE_DAYS = RULES["claim_submitted"][0][0]
PROVIDER = "Medivista TPA (mock)"


def now_iso() -> str:
    """Current local time, ISO format, seconds precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def due_date(submitted_on: str | None) -> str:
    """Settlement due date (15 days after submission), or 'not known' without a date."""
    try:
        return (date.fromisoformat(submitted_on[:10]) + timedelta(SETTLE_DAYS)).isoformat()
    except (TypeError, ValueError):
        return "not known"


def client_reference(thread_id: str, pack_hash: str) -> str:
    """Stable reference for one pack in one thread; also the idempotency key (no thread id leaks out)."""
    return f"cw-{hashlib.sha256(thread_id.encode()).hexdigest()[:12]}-{pack_hash}"


def approved_pack(state: AgentState) -> dict | None:
    """The current pack when the user approved exactly this content, else None."""
    pack = build_submission_pack(state)
    approval = state.get("submission_approval")
    return pack if approval and approval["hash"] == pack["hash"] else None


def submission_payload(state: AgentState, pack: dict, reference: str) -> tuple[dict | None, list[str]]:
    """The payer submission body (amounts in paise), or the missing fields that stop an online submission."""
    required = {"policy number": pack["policy_number"], "patient": pack["patient"], "claim type": pack["claim_type"],
                "admission date": pack["admission_date"], "discharge date": pack["discharge_date"],
                "claimed amount": pack["claimed_amount"]}
    missing = [name for name, value in required.items() if not value]
    if missing:
        return None, missing
    lines = _latest_facts(state, "hospital_bill").get("line_items") or []
    return {
        "client_reference": reference, "policy_number": pack["policy_number"], "member_name": pack["patient"],
        "acting_user": acting_user(state),  # the payer checks its own list of representatives (DEV-025)
        "claim_type": pack["claim_type"], "admission_date": pack["admission_date"],
        "discharge_date": pack["discharge_date"], "claimed_amount": pack["claimed_amount"] * 100,
        "line_items": [{"head": line["head"][:120], "amount": line["amount"] * 100} for line in lines if line["amount"] > 0],
        "documents": [{"id": d["id"][:64], "filename": d["filename"][:200], "doc_type": d["doc_type"]}
                      for d in pack["documents"]],
    }, []


def _submitted(state: AgentState, pack_hash: str, reference: str, claim: dict) -> tuple[dict, str]:
    """State update and reply once the payer holds the claim."""
    at = now_iso()
    day = (claim.get("submitted_at") or at)[:10]
    update = {
        "submission": {"route": "connector", "pack_hash": pack_hash, "client_reference": reference,
                       "status": "submitted", "claim_id": claim["id"], "submitted_at": claim.get("submitted_at") or at,
                       "error": None, "last_checked": at},
        "claim_info": {"submitted_on": day, "claim_number": claim["id"]},
        "notifications": [{"id": f"submitted-{claim['id']}", "at": at, "kind": "update",
                           "text": NOTE_SUBMITTED.format(claim_id=claim["id"]), "read": False}],
    }
    return update, SUBMITTED_REPLY.format(provider=PROVIDER, date=day, claim_id=claim["id"], due=due_date(day))


def _connection_lost(state: AgentState, code: str) -> tuple[dict, str]:
    """Mark the connection expired (consent removed or session ended) and tell the user to reconnect."""
    conn = state["connection"]
    at = now_iso()
    return {
        "connection": {**conn, "status": "expired"},
        "notifications": [{"id": f"conn-expired-{conn['case_id']}", "at": at, "kind": "warning",
                           "text": NOTE_CONNECTION_EXPIRED, "read": False}],
    }, REFUSED_REPLY.format(reason=REFUSAL_REASONS.get(code, REFUSAL_REASONS["VERIFICATION_REQUIRED"]))


def submit_via_connector(state: AgentState, thread_id: str) -> tuple[dict, str]:
    """Submit the approved pack through the connected account.

    Args:
        state: Current graph state.
        thread_id: Claim thread (part of the client reference).
    Returns:
        (state update, deterministic reply text).
    """
    blocked = authority_issues(state)
    if blocked:  # a withdrawn, expired or too narrow authority stops every submission (DEV-025)
        return {}, blocked[0][1]
    pack = approved_pack(state)
    if not pack:
        return {}, NEED_APPROVAL_REPLY
    previous = state.get("submission") or {}
    if previous.get("status") == "submitted" and previous.get("pack_hash") == pack["hash"]:
        return {}, ALREADY_SUBMITTED_REPLY.format(date=(previous.get("submitted_at") or "")[:10], claim_id=previous.get("claim_id"))
    conn = state.get("connection")
    if not conn or conn["status"] != "active":
        return {}, NEED_CONNECTION_REPLY

    reference = client_reference(thread_id, pack["hash"])
    body, missing = submission_payload(state, pack, reference)
    if missing:
        return {}, PACK_INCOMPLETE_REPLY.format(fields=", ".join(missing))
    try:
        # Look up first: an earlier attempt may have reached the payer even though its answer was lost.
        found = connector.find_claims(conn["case_id"], reference)
        claim = found[0] if found else connector.submit_claim(conn["case_id"], body, reference)
    except connector.ConnectorError as exc:
        if exc.status in (401, 403):
            return _connection_lost(state, exc.code)
        if exc.status == 422 and exc.code in REFUSAL_REASONS:
            return {"submission": {"route": "connector", "pack_hash": pack["hash"], "client_reference": reference,
                                   "status": "refused", "claim_id": None, "error": exc.code}}, \
                REFUSED_REPLY.format(reason=REFUSAL_REASONS[exc.code])
        claim = recover(conn["case_id"], reference) if exc.unclear else None
        if claim is None:
            return {"submission": {"route": "connector", "pack_hash": pack["hash"], "client_reference": reference,
                                   "status": "unconfirmed", "claim_id": None, "error": exc.code}}, UNCONFIRMED_REPLY
    return _submitted(state, pack["hash"], reference, claim)


def recover(case_id: str, reference: str) -> dict | None:
    """After an unclear failure, ask the payer whether the claim exists. None when it does not or cannot be told."""
    try:
        found = connector.find_claims(case_id, reference)
    except connector.ConnectorError:
        return None
    return found[0] if found else None


def reconcile(state: AgentState) -> tuple[dict, str | None]:
    """Settle an unconfirmed submission: adopt the claim if the payer has it (used by M1 and 'Check submission').

    Returns:
        (state update, reply text or None when there is nothing unconfirmed or the payer cannot be reached).
    """
    sub, conn = state.get("submission") or {}, state.get("connection")
    if sub.get("status") != "unconfirmed" or not conn or conn["status"] != "active":
        return {}, None
    claim = recover(conn["case_id"], sub["client_reference"])
    if claim is None:
        return {}, None
    return _submitted(state, sub["pack_hash"], sub["client_reference"], claim)


def record_manual(state: AgentState, data: dict, today: date | None = None) -> tuple[dict, str]:
    """Record that the user submitted the pack themselves (date required, claim number optional).

    Returns:
        (state update, deterministic reply). A missing, malformed or future date changes nothing.
    """
    today = today or date.today()
    blocked = authority_issues(state)
    if blocked:
        return {}, blocked[0][1]
    try:
        day = date.fromisoformat(str(data.get("submitted_on", "")))
    except ValueError:
        return {}, BAD_DATE_REPLY
    if day > today or day < today - timedelta(days=365):
        return {}, BAD_DATE_REPLY
    number = str(data.get("claim_number") or "").strip()[:60] or None
    pack = build_submission_pack(state)
    return {
        "submission": {"route": "manual", "pack_hash": pack["hash"], "client_reference": None, "status": "submitted",
                       "claim_id": number, "submitted_at": day.isoformat(), "error": None, "last_checked": None},
        "claim_info": {"submitted_on": day.isoformat(), "claim_number": number},
    }, MANUAL_RECORDED_REPLY.format(date=day.isoformat(), number=f", claim number {number}" if number else "",
                                    due=due_date(day.isoformat()))
