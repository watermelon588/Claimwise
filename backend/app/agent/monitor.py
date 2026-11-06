"""Monitoring (DEV-022), node M1 sync_connector: read the submitted claim from the connected account,
turn new queries, decisions and payments into insurer-letter records, and raise reminders from dates.

Runs at the start of every turn ("check on open"), and when the mock payer's signed webhook arrives.
Connector records reuse the insurer_letter facts shape, so C1 (query and decision) and P1 (payment) check
them exactly like uploaded letters. Provider text (query labels, reasons) is data, never instructions.
"""

import re
from datetime import date, timedelta

from app import connector
from app.agent.claim import parsed_docs, read_decision, read_query
from app.agent.grievance import dispute_view
from app.agent.onboarding import authority_status
from app.agent.prompts import (
    NOTE_CONNECTION_EXPIRED, NOTE_DECISION, NOTE_DISPUTE_REOPENED, NOTE_PAYMENT, NOTE_QUERY, REMIND_AUTHORITY_EXPIRY,
    REMIND_CHECK_LETTERS, REMIND_GRIEVANCE_DUE, REMIND_OVERDUE, REMIND_QUERY_DUE, REMIND_QUERY_LATE,
)
from app.agent.state import AgentState
from app.agent.submission import SETTLE_DAYS, due_date, now_iso, reconcile

# Words in a requested item -> the closest document type (first match wins).
REQUEST_TYPES = (
    ("discharge", "discharge_summary"), ("pharmacy", "pharmacy_bill"), ("medicine", "pharmacy_bill"),
    ("bill", "hospital_bill"), ("invoice", "hospital_bill"), ("report", "investigation_report"),
    ("investigation", "investigation_report"), ("lab", "investigation_report"), ("prescription", "prescription"),
    ("aadhaar", "id_proof"), ("identity", "id_proof"), ("id proof", "id_proof"), ("cheque", "cancelled_cheque"),
    ("claim form", "claim_form"),
)
QUERY_WARN_DAYS = 3
AUTHORITY_WARN_DAYS = 7


def request_type(item: dict) -> str:
    """Closest document type for one requested item, from its code and label; 'other' when unclear."""
    text = f"{item.get('code', '')} {item.get('label', '')}".replace("_", " ").lower()
    return next((doc_type for word, doc_type in REQUEST_TYPES if word in text), "other")


def _rupees(paise) -> int | None:
    """Payer amounts are in paise; facts are in whole rupees."""
    return paise // 100 if isinstance(paise, int) else None


def _key(text: str | None) -> str:
    """Safe id fragment from provider text (letters and digits only)."""
    return re.sub(r"[^A-Za-z0-9]", "", text or "")[:24]


def claim_documents(snapshot: dict) -> list[dict]:
    """Insurer-letter records for every query, the decision and every payment in a claim snapshot.

    Ids are stable per provider record, so a second read updates rather than duplicates.
    """
    claim_id = snapshot["id"]
    base = {"mime_type": "application/json", "path": "", "status": "parsed", "doc_type": "insurer_letter",
            "error": None, "source": "connector"}
    docs = []
    for q in snapshot["queries"]:
        raised = (q.get("raised_at") or "")[:10] or None
        docs.append({**base, "id": f"tpa-query-{_key(q['id'])}", "filename": f"TPA query {raised or ''}".strip(), "facts": {
            "letter_kind": "query", "letter_date": raised, "claim_number": claim_id,
            "requested_documents": [
                {"label": str(i.get("label") or i.get("description") or i.get("code") or "a document")[:200],
                 "doc_type": request_type(i)} for i in q["items"]],
            "due_on": q["due_at"][:10], "query_status": q["status"], "answered_on": (q.get("answered_at") or "")[:10] or None,
        }})
    d = snapshot.get("decision")
    if d:
        lines = [{"head": str(line.get("head") or "item")[:120], "claimed": _rupees(line.get("claimed")),
                  "approved": _rupees(line.get("approved")), "reason": line.get("deduction_reason") or None,
                  "clause": line.get("policy_clause") or None} for line in d.get("line_decisions") or []]
        docs.append({**base, "id": f"tpa-decision-{_key(claim_id)}-{_key(d['decided_at'])}",
                     "filename": f"TPA decision {d['decided_at'][:10]}", "facts": {
            "letter_kind": "decision", "letter_date": d["decided_at"][:10], "claim_number": claim_id,
            "outcome": d["outcome"], "claimed_amount": _rupees(snapshot["claimed_amount"]),
            "approved_amount": _rupees(d["approved_amount"]), "line_decisions": lines,
            "reason": d.get("rejection_reason"), "clause": d.get("policy_clause"),
        }})
    for p in snapshot["payments"]:
        docs.append({**base, "id": f"tpa-payment-{_key(p['utr'])}", "filename": f"TPA payment advice {p['paid_at'][:10]}",
                     "facts": {"letter_kind": "settlement", "letter_date": p["paid_at"][:10], "claim_number": claim_id,
                               "paid_amount": _rupees(p["amount"]), "utr": p["utr"], "paid_on": p["paid_at"][:10]}})
    return docs


def note_for(doc: dict) -> str:
    """Notification text for a new connector record."""
    f = doc["facts"]
    if f["letter_kind"] == "query":
        items = ", ".join(r["label"] for r in f["requested_documents"]) or "more information"
        return NOTE_QUERY.format(items=items, due=f["due_on"])
    if f["letter_kind"] == "decision":
        outcome = (f["outcome"] or "decided").replace("_", " ")
        return NOTE_DECISION.format(outcome=outcome, approved=f["approved_amount"], claimed=f["claimed_amount"])
    return NOTE_PAYMENT.format(amount=f["paid_amount"], date=f["paid_on"], utr=f["utr"])


def reminders(state: AgentState, today: date) -> list[dict]:
    """Date-based reminders that are due and not raised before (ids are deterministic, so each shows once)."""
    info, sub = state.get("claim_info") or {}, state.get("submission") or {}
    seen = {n["id"] for n in state.get("notifications", [])}
    at = now_iso()
    out = []

    def add(note_id: str, kind: str, text: str) -> None:
        """Queue one reminder unless it was already raised."""
        if note_id not in seen:
            out.append({"id": note_id, "at": at, "kind": kind, "text": text, "read": False})

    try:
        submitted = date.fromisoformat((info.get("submitted_on") or "")[:10])
    except ValueError:
        submitted = None
    letters = parsed_docs(state, "insurer_letter")
    # The 15 days run from the last document the insurer needs: not while a query is open, and from the answer.
    answers = [f["answered_on"] for f in (d.get("facts") or {} for d in letters) if f.get("answered_on")]
    start = max([submitted, *map(date.fromisoformat, answers)]) if submitted else None
    if submitted and read_decision(state) is None and read_query(state) is None:
        if today > start + timedelta(SETTLE_DAYS):
            add(f"rem-overdue-{start}", "warning", REMIND_OVERDUE.format(
                days=(today - start).days, due=due_date(start.isoformat())))
        elif sub.get("route") != "connector" and not letters and today >= submitted + timedelta(7):
            add(f"rem-letters-{submitted}", "reminder", REMIND_CHECK_LETTERS)

    for doc in parsed_docs(state, "insurer_letter"):
        f = doc.get("facts") or {}
        if f.get("letter_kind") != "query" or f.get("query_status") not in ("open", None) or not f.get("due_on"):
            continue
        try:
            due = date.fromisoformat(f["due_on"])
        except ValueError:
            continue
        if today > due:
            add(f"rem-{doc['id']}-late", "warning", REMIND_QUERY_LATE.format(days=(today - due).days, due=due))
        elif today >= due - timedelta(QUERY_WARN_DAYS):
            when = "today" if today == due else f"in {(due - today).days} days"
            add(f"rem-{doc['id']}-soon", "reminder", REMIND_QUERY_DUE.format(when=when, due=due))

    # DEV-026: no reply 14 days after the grievance; or a revised decision reopened the decision and payment check.
    view = dispute_view(state, today)
    if view and view["status"] == "grievance_filed" and not view["insurer_reply_on"] \
            and today > date.fromisoformat(view["grievance_due"]):
        add(f"rem-grievance-{view['grievance_filed_on']}", "warning", REMIND_GRIEVANCE_DUE.format(
            filed=view["grievance_filed_on"], ombudsman_from=view["ombudsman_from"]))
    if view and view["status"] == "revised":
        dispute = state.get("dispute") or {}
        step = "Ombudsman complaint" if dispute.get("ombudsman_hash") else "grievance"
        add(f"rem-revised-{read_decision(state)['letter_doc_id']}", "update",
            NOTE_DISPUTE_REOPENED.format(step=step, approved=view["approved_now"]))

    # DEV-025: a caregiver's authority that ends within a week.
    expires = (state.get("authority") or {}).get("expires_on")
    if expires and authority_status(state, today) == "active" \
            and date.fromisoformat(expires) <= today + timedelta(AUTHORITY_WARN_DAYS):
        patient = (state.get("user_role") or {}).get("patient_name") or "the patient"
        add(f"rem-authority-{expires}", "reminder", REMIND_AUTHORITY_EXPIRY.format(patient=patient, date=expires))
    return out


def sync_connector(state: AgentState, today: date | None = None) -> dict:
    """M1: reconcile an unconfirmed submission, read the submitted claim, and raise reminders.

    Never raises for provider problems: an unreachable gateway leaves state as it was (tried again next
    turn); an expired or revoked connection is marked so the user can reconnect.

    Returns:
        State update with new or changed connector documents, notifications, submission and connection.
    """
    update, notes = reconcile(state)[0], []
    notes += update.pop("notifications", [])
    sub = update.get("submission") or state.get("submission") or {}
    conn = state.get("connection")
    docs = {d["id"]: d for d in state.get("documents", [])}
    if sub.get("route") == "connector" and sub.get("status") == "submitted" and sub.get("claim_id") \
            and conn and conn["status"] == "active":
        at = now_iso()
        try:
            snapshot = connector.read_claim(conn["case_id"], sub["claim_id"])
        except connector.ConnectorError as exc:
            if exc.status in (401, 403):
                update["connection"] = {**conn, "status": "expired"}
                notes.append({"id": f"conn-expired-{conn['case_id']}", "at": at, "kind": "warning",
                              "text": NOTE_CONNECTION_EXPIRED, "read": False})
        else:
            fresh = [d for d in claim_documents(snapshot) if docs.get(d["id"]) != d]
            if fresh:
                update["documents"] = fresh
            notes += [{"id": f"note-{d['id']}", "at": at, "kind": "update", "text": note_for(d), "read": False}
                      for d in fresh if d["id"] not in docs]
            docs.update({d["id"]: d for d in fresh})
            update["submission"] = {**sub, "last_checked": at}
    # Reminders judge the claim as it is after this sync (a decision that just arrived ends "overdue").
    view = {**state, "documents": list(docs.values()),
            "claim_info": {**(state.get("claim_info") or {}), **(update.get("claim_info") or {})},
            "submission": update.get("submission") or state.get("submission")}
    notes += reminders(view, today or date.today())
    if notes:
        update["notifications"] = notes
    return update
