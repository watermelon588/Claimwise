"""Disputes (DEV-026): grievance letter, 14-day timer, Ombudsman eligibility and draft, and reopening.

Letters are built from the decision facts only, never by the model. The user approves each letter and sends it
(no public claimant API exists for grievance portals; research I-04). Status is derived from what the user did
(state.dispute) and from the letters on file, so a revised decision reopens only the decision and the payment
check: documents and the submission stay as they are.
"""

import hashlib
from datetime import date, timedelta

from app.agent.authority import actor
from app.agent.claim import build_submission_pack, parsed_docs, read_decision
from app.agent.prompts import (
    GRIEVANCE_POINT, GRIEVANCE_REJECTION_POINT, GRIEVANCE_TEMPLATE, GRIEVANCE_TOTAL_POINT, OMBUDSMAN_NO_REPLY,
    OMBUDSMAN_REASONS, OMBUDSMAN_REPLY_GIVEN, OMBUDSMAN_TEMPLATE,
)
from app.agent.state import AgentState
from app.agent.tools import RULES

GRIEVANCE_DAYS, OMBUDSMAN_WAIT_DAYS = (days for days, _ in RULES["grievance_filed"])  # 14 and 30
OMBUDSMAN_LIMIT = 50_00_000  # Rs 50 lakh (research P-14)
ONE_YEAR = 365  # Insurance Ombudsman Rules 2017, rule 14(3): within one year of the insurer's reply


def _day(text: str | None) -> date | None:
    """ISO date from text, or None."""
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def disputable(decision: dict | None) -> bool:
    """Something to dispute: a rejection, money deducted, or a deduction with no clause cited."""
    return bool(decision) and (decision["outcome"] == "rejected" or (decision.get("difference") or 0) > 0
                               or bool(decision["missing_clause"]))


def disputed_amount(decision: dict) -> int:
    """Rupees in dispute: the whole claim when rejected, else the amount deducted."""
    if decision["outcome"] == "rejected":
        return decision.get("claimed") or 0
    return max(decision.get("difference") or 0, 0)


def points(decision: dict) -> list[str]:
    """One line per point of disagreement, from the decision letter's own numbers and reasons."""
    if decision["outcome"] == "rejected":
        return [GRIEVANCE_REJECTION_POINT.format(reason=decision.get("reason") or "none given",
                                                 clause=decision.get("clause") or "none cited")]
    out = [GRIEVANCE_POINT.format(head=line["head"], claimed=line["claimed"], approved=line["approved"],
                                  deducted=line["deducted"], reason=line.get("reason") or "none given",
                                  clause=line.get("clause") or "none cited")
           for line in decision["lines"] if (line.get("deducted") or 0) > 0]
    if not out and (decision.get("difference") or 0) > 0:
        out.append(GRIEVANCE_TOTAL_POINT.format(deducted=decision["difference"]))
    return out


def insurer_reply(state: AgentState, since: date | None) -> dict | None:
    """The latest grievance reply letter dated on or after the grievance, or None."""
    replies = [d for d in parsed_docs(state, "insurer_letter")
               if (d.get("facts") or {}).get("letter_kind") == "grievance_reply"
               and since and (_day(d["facts"].get("letter_date")) or date.min) >= since]
    return replies[-1] if replies else None


def ombudsman_check(state: AgentState, today: date | None = None) -> tuple[bool, list[str]]:
    """Whether the Ombudsman route is open now, and the reasons when it is not.

    Rules used (research P-14, I-04): complain to the insurer first; then wait for its reply or 30 days; file within
    one year of the reply; amount in dispute up to Rs 50 lakh. Eligibility is checked, never promised.
    """
    today = today or date.today()
    decision, d = read_decision(state), state.get("dispute") or {}
    filed = _day(d.get("grievance_filed_on"))
    reasons = []
    if not filed:
        reasons.append(OMBUDSMAN_REASONS["no_grievance"])
    else:
        reply = insurer_reply(state, filed)
        reply_day = _day(reply["facts"].get("letter_date")) if reply else None
        if not reply_day and today < filed + timedelta(OMBUDSMAN_WAIT_DAYS):
            reasons.append(OMBUDSMAN_REASONS["too_early"].format(date=filed + timedelta(OMBUDSMAN_WAIT_DAYS)))
        if reply_day and today > reply_day + timedelta(ONE_YEAR):
            reasons.append(OMBUDSMAN_REASONS["too_late"].format(date=reply_day))
    if decision and disputed_amount(decision) > OMBUDSMAN_LIMIT:
        reasons.append(OMBUDSMAN_REASONS["over_limit"].format(amount=disputed_amount(decision)))
    return not reasons, reasons


def dispute_view(state: AgentState, today: date | None = None) -> dict | None:
    """Where the dispute stands, derived from the decision on file and the steps the user recorded.

    Returns:
        None when there is no decision, or nothing to dispute and no dispute started; else status (open,
        grievance_approved, grievance_filed, ombudsman_approved, ombudsman_filed, revised), amounts, dates,
        and Ombudsman eligibility.
    """
    decision = read_decision(state)
    d = state.get("dispute") or {}
    if not decision or not (disputable(decision) or d.get("decision_doc_id")):
        return None
    revised = bool(d.get("decision_doc_id")) and d["decision_doc_id"] != decision["letter_doc_id"]
    if revised:
        status = "revised"
    elif d.get("ombudsman_filed_on"):
        status = "ombudsman_filed"
    elif d.get("ombudsman_hash"):
        status = "ombudsman_approved"
    elif d.get("grievance_filed_on"):
        status = "grievance_filed"
    elif d.get("grievance_hash"):
        status = "grievance_approved"
    else:
        status = "open"
    filed = _day(d.get("grievance_filed_on"))
    reply = insurer_reply(state, filed) if filed and not revised else None
    eligible, reasons = ombudsman_check(state, today)
    return {
        "status": status, "disputable": disputable(decision), "disputed_amount": disputed_amount(decision),
        "grievance_filed_on": d.get("grievance_filed_on") or None,
        "grievance_due": (filed + timedelta(GRIEVANCE_DAYS)).isoformat() if filed else None,
        "ombudsman_from": (filed + timedelta(OMBUDSMAN_WAIT_DAYS)).isoformat() if filed else None,
        "insurer_reply_on": reply["facts"].get("letter_date") if reply else None,
        "ombudsman_filed_on": d.get("ombudsman_filed_on") or None,
        "ombudsman_eligible": eligible and status == "grievance_filed", "ombudsman_reasons": reasons,
        "approved_now": decision.get("approved"),
    }


def letter(state: AgentState, kind: str) -> tuple[str, str]:
    """The grievance or Ombudsman letter for the current decision, and a short hash of its text."""
    decision, pack = read_decision(state), build_submission_pack(state)
    info, d = state.get("claim_info") or {}, state.get("dispute") or {}
    claim_number = info.get("claim_number") or (state.get("submission") or {}).get("claim_id") or "not stated"
    common = dict(
        insurer=pack["insurer"] or "the insurer", tpa_line=f" (through {pack['tpa']})" if pack["tpa"] else "",
        claim_number=claim_number, policy_number=pack["policy_number"], patient=pack["patient"],
        decision_date=decision.get("letter_date") or "not stated", approved=decision.get("approved"),
        claimed=decision.get("claimed"), points="\n".join(points(decision)), submitted_by=actor(state),
    )
    if kind == "grievance":
        text = GRIEVANCE_TEMPLATE.format(**common, hospital=pack["hospital"] or "not stated",
                                         admission_date=pack["admission_date"] or "not stated")
    else:
        filed = _day(d.get("grievance_filed_on"))
        reply = insurer_reply(state, filed)
        text = OMBUDSMAN_TEMPLATE.format(
            **common, disputed=disputed_amount(decision), grievance_filed_on=d.get("grievance_filed_on"),
            grievance_ref=d.get("grievance_ref") or "none given",
            insurer_reply=OMBUDSMAN_REPLY_GIVEN.format(date=reply["facts"]["letter_date"]) if reply else OMBUDSMAN_NO_REPLY,
        )
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]
