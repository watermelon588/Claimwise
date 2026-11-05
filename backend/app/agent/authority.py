"""Claiming for someone else (DEV-025): the caregiver's authority record, its withdrawal, and the audit log.

Claimwise records authority; it cannot grant it. The insurer decides whether it accepts the representative
(research I-07, P-17, P-18). Pure Python, no model. Proof documents are read by O1 like any other upload.
"""

import uuid
from datetime import date, datetime

from app.agent.onboarding import authority_status, same_person
from app.agent.prompts import AUTHORITY_EXPIRED_ISSUE, AUTHORITY_SCOPE_ISSUE, AUTHORITY_WITHDRAWN_ISSUE
from app.agent.state import AgentState

BASES = ("policyholder", "insurer_registration", "power_of_attorney", "patient_consent")
SCOPES = ("submit_claim", "share_records", "receive_updates", "file_grievance")


def now_iso() -> str:
    """Current local time, ISO format, seconds precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def actor(state: AgentState) -> str:
    """Who is acting, in words: the patient, or the named caregiver and their relation."""
    role = state.get("user_role") or {}
    if role.get("role") != "caregiver":
        return f"{role.get('patient_name') or 'user'} (patient)"
    name = (state.get("authority") or {}).get("representative_name") or "caregiver"
    return f"{name} ({role.get('relation') or 'caregiver'} of {role.get('patient_name')})"


def audit(state: AgentState, action: str, detail: str) -> dict:
    """One audit log entry for an action taken now by the current user."""
    return {"id": f"audit-{uuid.uuid4().hex[:12]}", "at": now_iso(), "actor": actor(state),
            "action": action, "detail": detail[:300]}


def acting_user(state: AgentState) -> str | None:
    """The representative's name to send with a submission, or None when the patient acts."""
    if (state.get("user_role") or {}).get("role") != "caregiver":
        return None
    return (state.get("authority") or {}).get("representative_name")


def authority_issues(state: AgentState, today: date | None = None) -> list[tuple[str, str]]:
    """Block-level findings for C1: withdrawn, expired, or not covering submission. [(code, message)]."""
    status = authority_status(state, today)
    record = state.get("authority") or {}
    patient = (state.get("user_role") or {}).get("patient_name") or "the patient"
    if status == "withdrawn":
        return [("authority_withdrawn", AUTHORITY_WITHDRAWN_ISSUE.format(patient=patient, date=(record.get("withdrawn_at") or "")[:10]))]
    if status == "expired":
        return [("authority_expired", AUTHORITY_EXPIRED_ISSUE.format(patient=patient, date=record.get("expires_on")))]
    if status == "active" and "submit_claim" not in (record.get("scope") or []):
        return [("authority_scope", AUTHORITY_SCOPE_ISSUE)]
    return []


def validate_authority(state: AgentState, body: dict, today: date | None = None) -> tuple[dict | None, str | None]:
    """Check a caregiver's authority form against the role and the uploaded proof.

    Args:
        state: Current graph state.
        body: representative_name, basis, proof_doc_id (optional for policyholder), scope (list), expires_on.
        today: For tests.
    Returns:
        (authority record, None) when valid, else (None, a reason the user can act on).
    """
    today = today or date.today()
    role = state.get("user_role") or {}
    if role.get("role") != "caregiver":
        return None, "Authority is only needed when you act for someone else."
    patient = role["patient_name"]
    name = (body.get("representative_name") or "").strip()
    if not 2 <= len(name) <= 120:
        return None, "Enter your full name as the insurer knows you."
    if same_person(name, patient):
        return None, "Your name matches the patient. If you are the patient, choose 'The patient' instead."
    if body.get("basis") not in BASES:
        return None, "Choose how you are authorised."
    scope = sorted(set(body.get("scope") or []))
    if not scope or not set(scope) <= set(SCOPES):
        return None, "Choose what the authority covers."
    expires = body.get("expires_on") or None

    proof_id = body.get("proof_doc_id") or None
    if body["basis"] != "policyholder":
        proof = next((d for d in state.get("documents", []) if d["id"] == proof_id), None)
        if not proof or proof["status"] != "parsed" or proof.get("doc_type") != "authority_proof":
            return None, "Upload the proof (consent letter, registration or power of attorney) first."
        facts = proof.get("facts") or {}
        if facts.get("grantor_name") and not same_person(facts["grantor_name"], patient):
            return None, f"The proof is given by {facts['grantor_name']}, not by {patient}."
        if facts.get("representative_name") and not same_person(facts["representative_name"], name):
            return None, f"The proof names {facts['representative_name']} as the representative, not {name}."
        expires = expires or facts.get("valid_until")
    else:
        proof_id = None  # self-declared: the policy itself is the evidence; the audit log records it
    if expires:
        try:
            if date.fromisoformat(expires) < today:
                return None, f"This authority expired on {expires}."
        except ValueError:
            return None, "The expiry date does not look right."
    return {"representative_name": name, "basis": body["basis"], "proof_doc_id": proof_id, "scope": scope,
            "expires_on": expires, "status": "active", "recorded_at": now_iso(), "withdrawn_at": None}, None


def withdrawal(state: AgentState) -> dict:
    """State update when consent is withdrawn: pause work and cancel any approval made under it."""
    record = state.get("authority") or {}
    return {"authority": {**record, "status": "withdrawn", "withdrawn_at": now_iso()}, "submission_approval": None}


if __name__ == "__main__":
    # Smallest self-check: proof must name the patient; withdrawal cancels approval.
    s = {"user_role": {"role": "caregiver", "patient_name": "Ramesh Sharma", "relation": "son"},
         "documents": [{"id": "p", "status": "parsed", "doc_type": "authority_proof",
                        "facts": {"grantor_name": "Ramesh Sharma", "representative_name": "Aman Sharma"}}]}
    rec, err = validate_authority(s, {"representative_name": "Aman Sharma", "basis": "patient_consent",
                                      "proof_doc_id": "p", "scope": ["submit_claim"]})
    assert rec and not err
    assert validate_authority(s, {"representative_name": "Someone Else", "basis": "patient_consent",
                                  "proof_doc_id": "p", "scope": ["submit_claim"]})[0] is None
    assert withdrawal({**s, "authority": rec})["submission_approval"] is None
    print("ok")
