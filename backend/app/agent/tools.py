"""Agent tools. Deterministic Python only: the model calls them, it never does the maths itself."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from app.agent.claim import build_submission_pack, submission_blockers
from app.agent.prompts import APPROVE_SUBMISSION_QUESTION

# IRDAI 2024 circular timers (RESEARCH_DOSSIER P-04, P-13, P-14, P-15). Current applicability not verified.
RULES: dict[str, list[tuple[int, str]]] = {
    "claim_submitted": [(15, "Insurer must settle a non-cashless claim (else interest at bank rate + 2%)")],
    "grievance_filed": [
        (14, "Insurer must resolve the grievance with reasons"),
        (30, "Ombudsman route opens if still unresolved or the reply is unacceptable"),
    ],
    "ombudsman_award": [(30, "Insurer must comply with the Ombudsman award")],
}


@tool
def claim_deadline(
    event: Literal["claim_submitted", "grievance_filed", "ombudsman_award"], event_date: date
) -> list[dict]:
    """Return the regulatory due dates that follow a claim event.

    Args:
        event: What happened: claim_submitted, grievance_filed or ombudsman_award.
        event_date: The date it happened (YYYY-MM-DD).
    Returns:
        One entry per rule with the due date, days allowed and what is due.
    """
    return [
        {"due_date": (event_date + timedelta(days=d)).isoformat(), "days": d, "rule": rule}
        for d, rule in RULES[event]
    ]


@tool
def record_role(
    role: Literal["self", "caregiver"],
    patient_name: str,
    relation: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Save who the user is: the patient themself, or a caregiver helping the patient.

    Args:
        role: "self" if the user is the patient, "caregiver" if helping someone.
        patient_name: The patient's name as the user gave it.
        relation: How the user is related to the patient ("self" when role is self).
    Returns:
        A state update with user_role set and a confirmation tool message.
    """
    user_role = {"role": role, "patient_name": patient_name.strip(), "relation": relation.strip()}
    return Command(update={
        "user_role": user_role,
        "messages": [ToolMessage(f"Recorded role: {user_role}", tool_call_id=tool_call_id)],
    })


def _reply(text: str, tool_call_id: str, **update) -> Command:
    """Command that updates state and answers the tool call with a short message."""
    return Command(update={**update, "messages": [ToolMessage(text, tool_call_id=tool_call_id)]})


@tool
def update_claim(
    tool_call_id: Annotated[str, InjectedToolCallId],
    claim_type: Literal["cashless", "reimbursement"] | None = None,
    submitted_on: date | None = None,
    claim_number: str | None = None,
) -> Command:
    """Save claim facts the user states in chat. Only pass the fields the user actually gave.

    Args:
        claim_type: "cashless" (hospital bills the insurer) or "reimbursement" (user paid, claims back).
        submitted_on: Date the user submitted the claim to the insurer (YYYY-MM-DD).
        claim_number: Claim or reference number the insurer gave.
    Returns:
        A state update merging the given fields into claim_info.
    """
    info = {
        "claim_type": claim_type,
        "submitted_on": submitted_on.isoformat() if submitted_on else None,
        "claim_number": claim_number.strip() if claim_number else None,
    }
    saved = {k: v for k, v in info.items() if v is not None}
    return _reply(f"Saved claim facts: {saved}", tool_call_id, claim_info=info)


def request_pack_approval(state: dict) -> tuple[Literal["blocked", "approved", "declined"], list[str] | dict | None]:
    """Build the claim pack and pause for the user's approval (shared by the T1 tool and the X1 button).

    The run stops at interrupt(); POST /api/resume answers with {"approved": bool}. On resume the caller
    re-runs, rebuilding the same pack from the same state before interrupt() returns the answer.

    Returns:
        ("blocked", blocker texts), ("approved", the submission_approval record) or ("declined", None).
    """
    blockers = submission_blockers(state)
    if blockers:
        return "blocked", blockers
    pack = build_submission_pack(state)
    answer = interrupt({"type": "approve_submission", "question": APPROVE_SUBMISSION_QUESTION, "pack": pack})
    if not answer.get("approved"):
        return "declined", None
    return "approved", {"hash": pack["hash"], "approved_at": datetime.now().astimezone().isoformat(timespec="seconds")}


@tool
def prepare_submission(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Build the claim pack and ask the user to approve it. Call when the user wants to submit the claim.

    Returns:
        Blockers if the pack cannot be prepared yet; otherwise pauses for approval and records the
        approved pack hash, or notes that the user did not approve.
    """
    outcome, result = request_pack_approval(state)
    if outcome == "blocked":
        return _reply("Cannot prepare the claim yet: " + "; ".join(result), tool_call_id)
    if outcome == "declined":
        return _reply("The user did not approve the claim pack. Ask what they want to change.", tool_call_id)
    return _reply(
        "The user approved the claim pack. Tell them the next step from the Submission and Connection facts: "
        "'Submit for me' when connected, otherwise download the pack and submit it themselves, then press 'I submitted it'.",
        tool_call_id, submission_approval=result,
    )


TOOLS = [claim_deadline, record_role, update_claim, prepare_submission]
