"""Next-step buttons (DEV-019) and the X1 run_action node.

next_actions() derives the buttons for the current state, every turn, without the model. A press either
runs deterministic Python in X1 (prepare and approve the pack, submit, record a manual submission, check
for updates, and the Wave 4 choices: document versions, policy choice, balance claim, grievance and
Ombudsman letters), sends a fixed instruction to the agent (explain the decision, and so on), or is handled
in the browser (upload, download, connect, focus the message box).
"""

from datetime import date, timedelta
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import interrupt

from app.agent.authority import audit, now_iso
from app import connector
from app.agent.authority import authority_issues
from app.agent.claim import (
    NOT_IN_PACK, confirmed_policies, confirmed_policy, covers, parsed_docs, read_decision, read_query,
    submission_blockers,
)
from app.agent.grievance import GRIEVANCE_DAYS, dispute_view, letter, ombudsman_check
from app.agent.prompts import (
    ACTION_MESSAGES, ALREADY_SENT_DRAFT, ALREADY_SENT_LINE, ALREADY_SUBMITTED_REPLY, APPROVAL_RESET_NOTE,
    APPROVE_LETTER_QUESTION, BAD_DISPUTE_DATE_REPLY, BALANCE_STARTED_REPLY, CHECKED_REPLY, DOC_TYPE_LABELS,
    GRIEVANCE_FILED_REPLY, GRIEVANCE_SCOPE_REPLY, LETTER_APPROVED_REPLY, LETTER_NOT_APPROVED_REPLY, NO_BALANCE_REPLY,
    NO_DISPUTE_REPLY, NOT_ELIGIBLE_REPLY, NOTHING_ALREADY_SENT_REPLY, NOTHING_NEW, NOTHING_YET_REPLY,
    OMBUDSMAN_FILED_REPLY, PACK_APPROVED_REPLY, PACK_BLOCKED_REPLY, PACK_NOT_APPROVED_REPLY, POLICY_CHOSEN_REPLY,
    POLICY_NOT_FOR_PATIENT, ROUTE_CONNECTOR, ROUTE_MANUAL, STALE_CHOICE_REPLY, UNCONFIRMED_REPLY, NOT_AT_PAYER_REPLY,
    VERSION_KEPT_REPLY, VERSION_REPLACED_REPLY, BAD_QUERY_DATE_REPLY, NOTE_CONNECTION_EXPIRED, QUERY_ANSWERED_REPLY,
    QUERY_NOT_OPEN_REPLY, QUERY_REPLY_LETTER, QUERY_REPLY_LINE, QUERY_SEND_UNCLEAR_REPLY, QUERY_SENT_REPLY,
)
from app.agent.state import AgentState
from app.agent.submission import (
    SETTLE_DAYS, connection_lost, due_date, not_at_payer, provider_name, reconcile, record_manual,
    submit_via_connector,
)
from app.agent.tools import request_pack_approval
from app.config import get_settings

LABELS = {
    "prepare_pack": "Prepare my claim pack",
    "review_pack": "Review the updated pack",
    "submit_connector": "Submit for me",
    "retry_submit": "Try submitting again",
    "check_submission": "Check submission",
    "connect": "Connect my insurer account",
    "download_pdf": "Download PDF",
    "download_eml": "Download email draft",
    "submitted_manually": "I submitted it",
    "how_to_submit": "How do I submit?",
    "change_pack": "Change something in the pack",
    "check_updates": "Check for updates",
    "upload_letter": "I got a letter: upload it",
    "nothing_yet": "Nothing yet",
    "explain_query": "What do they need?",
    "upload_requested": "Upload what they asked for",
    "explain_decision": "Explain the decision",
    "upload_statement": "Upload bank statement",
    "explain_payment": "Explain the payment check",
    "upload_fix": "Upload a corrected document",
    "replace_version": "Use the new version",
    "keep_version": "Keep both files",
    "draft_already_sent": "Draft a reply: already sent",
    "choose_policy": "Claim on this policy",
    "start_balance_claim": "Claim the balance on another policy",
    "draft_grievance": "Draft a grievance letter",
    "grievance_sent": "I sent the grievance",
    "draft_ombudsman": "Draft the Ombudsman complaint",
    "ombudsman_sent": "I filed with the Ombudsman",
    "send_query_reply": "Send the documents to the insurer",
    "query_answered": "I sent what they asked for",
    "other": "Something else",
}
# Presses that run in X1 without the model; the button id is stored in requested_action.
DETERMINISTIC = {"prepare_pack", "review_pack", "submit_connector", "retry_submit", "check_submission",
                 "submitted_manually", "check_updates", "nothing_yet", "replace_version", "keep_version",
                 "draft_already_sent", "choose_policy", "start_balance_claim", "draft_grievance", "grievance_sent",
                 "draft_ombudsman", "ombudsman_sent", "send_query_reply", "query_answered"}
# Block issues that a button answers directly, so they do not also ask for a corrected upload.
CHOICE_CODES = {"version_choice", "choose_policy", "authority_withdrawn", "authority_expired", "authority_scope"}
DECIDED_STAGES = ("decided", "payment_reported", "payment_mismatch", "payment_verified")
Kind = Literal["send", "upload", "download", "form", "connect", "focus"]


def _button(action_id: str, kind: Kind = "send", label: str | None = None, **extra) -> dict:
    """One button for the API response."""
    return {"id": action_id, "label": label or LABELS[action_id], "kind": kind, **extra}


def connector_page() -> str | None:
    """URL of the connector page when insurer connections are enabled on this server, else None."""
    settings = get_settings()
    return settings.connector_page_url if settings.connector_url else None


def next_actions(state: AgentState) -> list[dict]:
    """Buttons for what the user can do next, derived only from state (and whether connectors are enabled).

    Every caller (API response, A1 prompt, off-topic reply, /api/action check) gets the same list.

    Args:
        state: Graph state after the turn.
    Returns:
        Ordered buttons; empty while onboarding is incomplete (the setup form leads).
    """
    if not (state.get("onboarding") or {}).get("complete") or not state.get("claim"):
        return []
    claim, sub = state["claim"], state.get("submission") or {}
    conn = state.get("connection") or {}
    connected = conn.get("status") == "active"
    stage = claim["stage"]
    page = connector_page()
    out = version_buttons(state)

    if stage == "preparing":
        blockers = submission_blockers(state)
        out += policy_buttons(state, claim)
        for doc_type in claim["checklist"]["missing_required"]:
            out.append(_button(f"upload_{doc_type}", "upload", f"Upload {DOC_TYPE_LABELS.get(doc_type, doc_type)}"))
        if any(i["severity"] == "block" and i["code"] not in CHOICE_CODES for i in claim["issues"]):
            out.append(_button("upload_fix", "upload"))
        if not blockers:
            invalidated = any(i["code"] == "approval_invalidated" for i in claim["issues"])
            out.append(_button("review_pack" if invalidated else "prepare_pack"))
    elif stage == "approved_to_submit":
        same_pack = sub.get("pack_hash") == claim["pack_hash"]
        if same_pack and sub.get("status") == "unconfirmed":
            out += [_button("check_submission"), _button("retry_submit")]
        elif connected and not (same_pack and sub.get("status") == "refused"):
            out.append(_button("submit_connector"))
        elif page and not connected:
            out.append(_button("connect", "connect", href=page))
        out += [_button("download_pdf", "download", format="pdf"), _button("download_eml", "download", format="eml"),
                _button("submitted_manually", "form"), _button("how_to_submit"), _button("change_pack")]
    elif stage == "submitted":
        if sub.get("route") == "connector" and connected:
            out.append(_button("check_updates"))
        out += [_button("upload_letter", "upload"), _button("nothing_yet")]
    elif stage == "query_raised":
        out += [_button("upload_requested", "upload"), _button("explain_query")]
        if any(i["code"] == "repeated_request" for i in claim["issues"]):
            out.append(_button("draft_already_sent"))
        out += query_buttons(state, connected)
        if sub.get("route") == "connector" and connected:
            out.append(_button("check_updates"))
    elif stage == "decided":
        out.append(_button("explain_decision"))
        payment = claim.get("payment") or {}
        if payment.get("status") in ("awaiting", "reported"):
            out.append(_button("upload_statement", "upload"))
        if sub.get("route") == "connector" and connected:
            out.append(_button("check_updates"))
    elif stage in ("payment_reported", "payment_mismatch"):
        out += [_button("upload_statement", "upload"), _button("explain_payment")]
    elif stage == "payment_verified":
        out.append(_button("explain_payment"))
    if stage in DECIDED_STAGES:
        out += dispute_buttons(state) + balance_buttons(state)
    out.append(_button("other", "focus"))
    return out


def version_buttons(state: AgentState) -> list[dict]:
    """Replace or keep both, for the first upload waiting on that choice (DEV-023)."""
    by_id = {d["id"]: d for d in state.get("documents", [])}
    new = next((d for d in state.get("documents", []) if d["status"] == "parsed"
                and d.get("version_choice") == "pending" and d.get("version_of") in by_id), None)
    if not new:
        return []
    old = by_id[new["version_of"]]["filename"]
    return [_button("replace_version", label=f"Use {new['filename']} instead of {old}", data={"doc_id": new["id"]}),
            _button("keep_version", label=f"Keep both {old} and {new['filename']}", data={"doc_id": new["id"]})]


def policy_buttons(state: AgentState, claim: dict) -> list[dict]:
    """One button per policy covering the patient, while the claimant has not chosen where to claim (DEV-024)."""
    if not any(i["code"] == "choose_policy" for i in claim["issues"]):
        return []
    patient = (state.get("user_role") or {}).get("patient_name")
    return [_button("choose_policy", label=f"Claim on {p['insurer']} {p['policy_number']}", data={"doc_id": p["doc_id"]})
            for p in confirmed_policies(state) if covers(p, patient)]


def balance_buttons(state: AgentState) -> list[dict]:
    """A balance claim on each other policy covering the patient, once a decision left money unpaid (DEV-024)."""
    decision = read_decision(state)
    if not decision or ((decision.get("difference") or 0) <= 0 and decision["outcome"] != "rejected"):
        return []
    return [_button("start_balance_claim", label=f"Claim the balance on {p['insurer']} {p['policy_number']}",
                    data={"doc_id": p["doc_id"]}) for p in balance_policies(state)]


def balance_policies(state: AgentState) -> list[dict]:
    """Policies that cover the patient and were not claimed on in this or an earlier round."""
    patient = (state.get("user_role") or {}).get("patient_name")
    used = {h["policy_doc_id"] for h in state.get("claims_history") or []}
    used.add((confirmed_policy(state) or {}).get("doc_id"))
    return [p for p in confirmed_policies(state) if covers(p, patient) and p["doc_id"] not in used]


def query_documents(state: AgentState) -> tuple[list[dict], list[str]]:
    """The documents that answer the open query (latest of each requested type) and the items still missing.

    An item that maps to no known type is answered by any claim document uploaded after the query arrived.
    """
    query = read_query(state)
    letter = _doc(state, (query or {}).get("letter_doc_id")) or {}
    later = [d for d in parsed_docs(state) if d["doc_type"] not in NOT_IN_PACK
             and (d.get("uploaded_at") or "") > (letter.get("uploaded_at") or "")]
    docs, missing = {}, []
    for item in (query or {}).get("requested", []):
        found = parsed_docs(state, item["doc_type"]) if item["doc_type"] != "other" else later
        if found:
            docs[found[-1]["id"]] = {**found[-1], "label": item["label"]}
        else:
            missing.append(item["label"])
    return list(docs.values()), missing


def query_buttons(state: AgentState, connected: bool) -> list[dict]:
    """Answer the open query: send through the connected account (connector queries), or record that the user did."""
    query = read_query(state)
    letter = _doc(state, (query or {}).get("letter_doc_id"))
    if not letter:
        return []
    if letter.get("source") != "connector":
        return [_button("query_answered", "form", form="dated")]
    docs, missing = query_documents(state)
    if not connected or missing or not docs or (state.get("submission") or {}).get("route") != "connector":
        return []
    return [_button("send_query_reply", label=f"Send {len(docs)} document(s) to the insurer")]


def dispute_buttons(state: AgentState) -> list[dict]:
    """The one next dispute step: draft the grievance, record it, draft the Ombudsman complaint, record it (DEV-026)."""
    view = dispute_view(state)
    if not view:
        return []
    status = view["status"]
    if status == "open" or (status == "revised" and view["disputable"]):
        return [_button("draft_grievance")]
    if status == "grievance_approved":
        return [_button("grievance_sent", "form", form="dated")]
    if status == "grievance_filed":
        return [_button("draft_ombudsman")]
    if status == "ombudsman_approved":
        return [_button("ombudsman_sent", "form", form="dated")]
    return []


def current_step(state: AgentState) -> str:
    """The first next step in words, for fixed replies such as the off-topic one."""
    steps = [a["label"] for a in next_actions(state) if a["id"] != "other"]
    if not steps:
        return "finish setting up your claim with the form on screen"
    return steps[0][0].lower() + steps[0][1:]


def action_input(action_id: str, data: dict | None) -> dict | None:
    """Graph input for a button press, or None when the id is not a server-side action.

    Deterministic presses carry requested_action; model presses send a fixed instruction as the message.
    Both are HumanMessages named 'action' so I1 never classifies them as free text.
    """
    if action_id in DETERMINISTIC:
        return {"messages": [HumanMessage(LABELS[action_id], name="action")],
                "requested_action": {"id": action_id, "data": data or {}}}
    if action_id in ACTION_MESSAGES:
        return {"messages": [HumanMessage(ACTION_MESSAGES[action_id], name="action")]}
    return None


def _prepare(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """Build the pack and pause for approval (same helper as the prepare_submission tool)."""
    outcome, result = request_pack_approval(state)
    if outcome == "blocked":
        return {}, PACK_BLOCKED_REPLY.format(blockers="\n".join(f"- {b}" for b in result))
    if outcome == "declined":
        return {}, PACK_NOT_APPROVED_REPLY
    connected = (state.get("connection") or {}).get("status") == "active"
    route = ROUTE_CONNECTOR.format(provider=provider_name(state)) if connected else ROUTE_MANUAL
    return {"submission_approval": result}, PACK_APPROVED_REPLY.format(route=route)


def _check_submission(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """Look up an unconfirmed submission at the payer."""
    update, text = reconcile(state)
    if text:
        return update, text
    sub = state.get("submission") or {}
    if sub.get("status") == "submitted":
        return {}, ALREADY_SUBMITTED_REPLY.format(date=(sub.get("submitted_at") or "")[:10], claim_id=sub.get("claim_id"))
    # The payer answered and does not have it: say so and point to the retry, instead of "check again later".
    if not_at_payer(state):
        return {"submission": {**sub, "error": "NOT_AT_PAYER"}}, NOT_AT_PAYER_REPLY.format(provider=provider_name(state))
    return {}, UNCONFIRMED_REPLY


def _check_updates(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """M1 already read the claim at the start of this turn; report what it found."""
    sub = state.get("submission") or {}
    news = [n["text"] for n in state.get("notifications", [])
            if n["kind"] == "update" and sub.get("last_checked") and n["at"] == sub["last_checked"]]
    due = due_date((state.get("claim_info") or {}).get("submitted_on"))
    return {}, CHECKED_REPLY.format(news=" ".join(news) or NOTHING_NEW.format(due=due))


def _doc(state: AgentState, doc_id: str | None) -> dict | None:
    """The document record with this id, or None."""
    return next((d for d in state.get("documents", []) if d["id"] == doc_id), None)


def _reset_approval(state: AgentState) -> tuple[dict, str]:
    """Cancel a pack approval that the change makes stale, while nothing has been submitted yet.

    Returns:
        (state update, note for the reply); empty when there is nothing to cancel.
    """
    submitted = (state.get("submission") or {}).get("status") == "submitted"
    if state.get("submission_approval") and not submitted:
        return {"submission_approval": None}, APPROVAL_RESET_NOTE
    return {}, ""


def _version(state: AgentState, data: dict, thread_id: str, replace: bool) -> tuple[dict, str]:
    """DEV-023: the new upload replaces the old one (old becomes superseded) or both stay in the pack."""
    new = _doc(state, data.get("doc_id"))
    old = _doc(state, (new or {}).get("version_of"))
    if not new or not old or new.get("version_choice") != "pending":
        return {}, STALE_CHOICE_REPLY
    reset, note = _reset_approval(state)
    if replace:
        version = (old.get("version") or 1) + 1
        docs = [{**old, "status": "superseded"}, {**new, "version": version, "version_choice": "replaced"}]
        return {**reset, "documents": docs}, VERSION_REPLACED_REPLY.format(
            new=new["filename"], old=old["filename"], version=version, approval=note)
    return {**reset, "documents": [{**new, "version_choice": "kept"}]}, VERSION_KEPT_REPLY.format(
        old=old["filename"], new=new["filename"], approval=note)


def _already_sent(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-023: a reply the user can send when the insurer asks again for documents already given."""
    query = read_query(state)
    items = [i for i in (query or {}).get("requested", []) if i.get("already_provided")]
    if not items:
        return {}, NOTHING_ALREADY_SENT_REPLY
    claim_number = (state.get("claim_info") or {}).get("claim_number") or (state.get("submission") or {}).get("claim_id")
    lines = "\n".join(ALREADY_SENT_LINE.format(label=i["label"], date=i.get("provided_on") or "earlier",
                                               filename=i["already_provided"]) for i in items)
    return {}, ALREADY_SENT_DRAFT.format(claim_number=claim_number or "not stated", lines=lines)


def _choose_policy(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-024: the claimant chooses which policy this claim goes to first."""
    policy = next((p for p in confirmed_policies(state) if p["doc_id"] == data.get("doc_id")), None)
    if not policy:
        return {}, STALE_CHOICE_REPLY
    patient = (state.get("user_role") or {}).get("patient_name")
    if not covers(policy, patient):
        return {}, POLICY_NOT_FOR_PATIENT.format(patient=patient)
    reset, note = _reset_approval(state)
    return {**reset, "claim_info": {"policy_doc_id": policy["doc_id"]}}, POLICY_CHOSEN_REPLY.format(
        insurer=policy["insurer"], policy_number=policy["policy_number"]) + note


def _balance(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-024: close this round and start a balance claim on another policy, with the first decision as evidence.

    The first insurer's letters and bank statements are archived (kept, but out of the live decision and
    payment checks) and enclosed in the new pack; the hospital documents stay as they are.
    """
    target = next((p for p in balance_policies(state) if p["doc_id"] == data.get("doc_id")), None)
    decision = read_decision(state)
    if not target or not decision:
        return {}, NO_BALANCE_REPLY
    current, info = confirmed_policy(state) or {}, state.get("claim_info") or {}
    claimed, approved = decision["claimed"] or 0, decision["approved"] or 0
    claim_number = info.get("claim_number") or (state.get("submission") or {}).get("claim_id") or "not stated"
    history = [*(state.get("claims_history") or []), {
        "round": info.get("round") or 1, "policy_doc_id": current.get("doc_id"), "insurer": current.get("insurer"),
        "policy_number": current.get("policy_number"), "claim_number": claim_number,
        "submitted_on": info.get("submitted_on") or None, "outcome": decision["outcome"], "claimed": claimed,
        "approved": approved, "closed_at": now_iso(),
    }]
    archived = [{**d, "status": "archived"} for d in state.get("documents", [])
                if d["status"] == "parsed" and d["doc_type"] in ("insurer_letter", "bank_statement")]
    balance = {"previous": current.get("insurer") or "the first insurer", "claim_number": claim_number,
               "approved": approved, "claimed": claimed, "balance": claimed - approved}
    # "" clears a field under the merge_dict reducer (None would keep the old value).
    cleared_dispute = dict.fromkeys(("decision_doc_id", "grievance_hash", "grievance_approved_at", "grievance_filed_on",
                                     "grievance_ref", "ombudsman_hash", "ombudsman_approved_at", "ombudsman_filed_on",
                                     "ombudsman_ref"), "")
    return {
        "documents": archived, "claims_history": history, "submission": None, "submission_approval": None,
        "dispute": cleared_dispute,
        "claim_info": {"policy_doc_id": target["doc_id"], "round": len(history) + 1, "balance_of": balance,
                       "submitted_on": "", "claim_number": ""},
    }, BALANCE_STARTED_REPLY.format(insurer=target["insurer"], policy_number=target["policy_number"],
                                    balance=balance["balance"], previous=balance["previous"])


def _approve_letter(state: AgentState, kind: str) -> tuple[str, str] | None:
    """Pause with the letter for approval; returns (text, hash) when approved, else None.

    On resume X1 re-runs and rebuilds the same letter from the same state before interrupt() returns.
    """
    text, digest = letter(state, kind)
    answer = interrupt({"type": "approve_letter", "kind": kind, "question": APPROVE_LETTER_QUESTION[kind], "letter": text})
    return (text, digest) if answer.get("approved") else None


def _draft_grievance(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-026: the grievance letter from the decision facts, approved by the user, sent by the user."""
    view = dispute_view(state)
    if not view or not view["disputable"]:
        return {}, NO_DISPUTE_REPLY
    record = state.get("authority") or {}
    if (state.get("user_role") or {}).get("role") == "caregiver" and "file_grievance" not in (record.get("scope") or []):
        return {}, GRIEVANCE_SCOPE_REPLY
    approved = _approve_letter(state, "grievance")
    if not approved:
        return {}, LETTER_NOT_APPROVED_REPLY
    text, digest = approved
    dispute = {"decision_doc_id": read_decision(state)["letter_doc_id"], "grievance_hash": digest,
               "grievance_approved_at": now_iso(), "grievance_filed_on": "", "grievance_ref": "", "ombudsman_hash": "",
               "ombudsman_approved_at": "", "ombudsman_filed_on": "", "ombudsman_ref": ""}
    return {"dispute": dispute}, f"{LETTER_APPROVED_REPLY['grievance']}\n\n{text}"


def _draft_ombudsman(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-026: check Ombudsman eligibility, then the complaint letter for approval."""
    eligible, reasons = ombudsman_check(state)
    if not eligible:
        return {}, NOT_ELIGIBLE_REPLY.format(reasons="\n".join(f"- {r}" for r in reasons))
    approved = _approve_letter(state, "ombudsman")
    if not approved:
        return {}, LETTER_NOT_APPROVED_REPLY
    text, digest = approved
    return {"dispute": {"ombudsman_hash": digest, "ombudsman_approved_at": now_iso(), "ombudsman_filed_on": "",
                        "ombudsman_ref": ""}}, f"{LETTER_APPROVED_REPLY['ombudsman']}\n\n{text}"


def _send_query_reply(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """Send the documents the insurer asked for through the connected account, after the user approves the list."""
    blocked = authority_issues(state)
    if blocked:  # a withdrawn, expired or too narrow authority stops every write to the insurer (DEV-025)
        return {}, blocked[0][1]
    query, sub, conn = read_query(state), state.get("submission") or {}, state.get("connection") or {}
    docs, missing = query_documents(state)
    if not query or missing or not docs or conn.get("status") != "active" or not sub.get("claim_id"):
        return {}, STALE_CHOICE_REPLY
    claim_number = (state.get("claim_info") or {}).get("claim_number") or sub["claim_id"]
    lines = "\n".join(QUERY_REPLY_LINE.format(label=d["label"], filename=d["filename"]) for d in docs)
    text = QUERY_REPLY_LETTER.format(letter_date=query.get("letter_date") or "", claim_number=claim_number, lines=lines)
    # Pause for approval: nothing goes to the insurer until the user approves this exact list.
    answer = interrupt({"type": "approve_letter", "kind": "query_reply", "question": APPROVE_LETTER_QUESTION["query_reply"],
                        "letter": text})
    if not answer.get("approved"):
        return {}, LETTER_NOT_APPROVED_REPLY
    try:
        connector.answer_query(conn["case_id"], sub["claim_id"], [
            {"id": d["id"][:64], "filename": d["filename"][:200], "doc_type": d["doc_type"]} for d in docs])
    except connector.ConnectorError as exc:
        if exc.status in (401, 403):
            return connection_lost(state, exc.code)[0], NOTE_CONNECTION_EXPIRED
        return {}, QUERY_NOT_OPEN_REPLY if exc.code == "QUERY_NOT_OPEN" else QUERY_SEND_UNCLEAR_REPLY
    today = date.today().isoformat()
    letter = _doc(state, query["letter_doc_id"])
    answered = {**letter, "facts": {**letter["facts"], "query_status": "answered", "answered_on": today}}
    return {"documents": [answered]}, QUERY_SENT_REPLY.format(count=len(docs), provider=provider_name(state),
                                                              days=SETTLE_DAYS, due=due_date(today))


def _query_answered(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """Record the date the user sent the insurer what its uploaded query letter asked for."""
    query = read_query(state)
    letter = _doc(state, (query or {}).get("letter_doc_id"))
    if not letter:
        return {}, STALE_CHOICE_REPLY
    try:
        day = date.fromisoformat(str(data.get("date", "")))
    except ValueError:
        return {}, BAD_QUERY_DATE_REPLY
    if day > date.today() or day.isoformat() < (query.get("letter_date") or "")[:10]:
        return {}, BAD_QUERY_DATE_REPLY
    answered = {**letter, "facts": {**letter["facts"], "query_status": "answered", "answered_on": day.isoformat()}}
    return {"documents": [answered]}, QUERY_ANSWERED_REPLY.format(date=day.isoformat(), due=due_date(day.isoformat()))


def _sent_on(state: AgentState, data: dict, today: date | None = None) -> tuple[str, str] | None:
    """Validated (date, reference) from the 'I sent it' form: not before the decision, not in the future."""
    today = today or date.today()
    try:
        day = date.fromisoformat(str(data.get("date", "")))
    except ValueError:
        return None
    decided = (read_decision(state) or {}).get("letter_date") or ""
    if day > today or day.isoformat() < decided[:10]:
        return None
    return day.isoformat(), str(data.get("reference") or "").strip()[:60]


def _grievance_sent(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-026: record the date the grievance went out; the 14-day and 30-day timers start here."""
    sent = _sent_on(state, data)
    if not sent:
        return {}, BAD_DISPUTE_DATE_REPLY
    day, ref = sent
    due = (date.fromisoformat(day) + timedelta(GRIEVANCE_DAYS)).isoformat()
    return {"dispute": {"grievance_filed_on": day, "grievance_ref": ref}}, GRIEVANCE_FILED_REPLY.format(
        date=day, ref=f", reference {ref}" if ref else "", due=due)


def _ombudsman_sent(state: AgentState, data: dict, thread_id: str) -> tuple[dict, str]:
    """DEV-026: record the date the Ombudsman complaint was filed."""
    sent = _sent_on(state, data)
    if not sent:
        return {}, BAD_DISPUTE_DATE_REPLY
    day, ref = sent
    return {"dispute": {"ombudsman_filed_on": day, "ombudsman_ref": ref}}, OMBUDSMAN_FILED_REPLY.format(
        date=day, ref=f", reference {ref}" if ref else "")


HANDLERS = {
    "prepare_pack": _prepare,
    "review_pack": _prepare,
    "submit_connector": lambda state, data, tid: submit_via_connector(state, tid),
    "retry_submit": lambda state, data, tid: submit_via_connector(state, tid),
    "check_submission": _check_submission,
    "submitted_manually": lambda state, data, tid: record_manual(state, data),
    "check_updates": _check_updates,
    "nothing_yet": lambda state, data, tid: ({}, NOTHING_YET_REPLY.format(
        due=due_date((state.get("claim_info") or {}).get("submitted_on")))),
    "replace_version": lambda state, data, tid: _version(state, data, tid, replace=True),
    "keep_version": lambda state, data, tid: _version(state, data, tid, replace=False),
    "draft_already_sent": _already_sent,
    "choose_policy": _choose_policy,
    "start_balance_claim": _balance,
    "draft_grievance": _draft_grievance,
    "grievance_sent": _grievance_sent,
    "draft_ombudsman": _draft_ombudsman,
    "ombudsman_sent": _ombudsman_sent,
    "send_query_reply": _send_query_reply,
    "query_answered": _query_answered,
}


def run_action(state: AgentState, config: RunnableConfig) -> dict:
    """X1: run one button press without the model and reply with fixed text. Clears requested_action.

    Returns:
        The handler's state update plus the reply; C1 runs again afterwards so the stage is current.
    """
    request = state.get("requested_action") or {}
    update, text = HANDLERS[request["id"]](state, request.get("data") or {}, config["configurable"]["thread_id"])
    if update:  # every press that changed the claim goes into the audit log (DEV-025)
        update["audit"] = [audit(state, request["id"], f"{LABELS[request['id']]}: {text.splitlines()[0]}")]
    return {**update, "messages": [AIMessage(text)], "requested_action": None}


def route_turn(state: AgentState) -> str:
    """Where the turn goes after the claim review (C1, and P1 when it ran).

    A pressed button runs in X1; a turn that already has its reply (X1 ran, C1 refreshed) ends; free text
    the user typed is classified first (I1); uploads, button instructions and tool results go to A1.
    """
    if state.get("requested_action"):
        return "run_action"
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    if last is None or (isinstance(last, AIMessage) and not last.tool_calls):
        return END  # the turn has its reply, or a refresh of an empty thread
    if isinstance(last, HumanMessage) and not last.name:
        return "classify_intent"
    return "agent"
