"""Payment verification (P1): did the approved money actually reach the right place? Pure Python, no model.

"Settled" on a portal or letter is not proof of payment (RESEARCH_DOSSIER C-13), so a reimbursement
is only verified when a matching credit shows up on the user's bank statement.

Sources today are uploaded documents: the insurer's settlement letter and the user's bank statement.
Every payment and credit record carries `source`, so connector data (MOCK-003 claim payments and bank
credits, after the user links accounts) can join the same lists later without changing the checks.
"""

from collections import Counter
from datetime import date, timedelta
from typing import Literal

from app.agent.claim import _issue, parsed_docs
from app.agent.state import AgentState
from app.agent.tools import RULES

SETTLE_DAYS = RULES["claim_submitted"][0][0]  # 15 days, IRDAI 2024 (P-04)
# ponytail: fixed 30-day search window after the payment or decision date; widen if real statements lag.
CREDIT_WINDOW_DAYS = 30
STAGE_FOR = {"reported": "payment_reported", "verified": "payment_verified", "mismatch": "payment_mismatch"}
BANK_TRACE = (
    "If the insurer confirms the transfer went to the right account, ask your bank to trace the UTR. "
    "Raise a written complaint with the bank first if the problem is on its side. "
    "If it remains unresolved and is eligible, use the RBI Integrated Ombudsman Scheme."
)


def _day(text: str | None) -> date | None:
    """Parse a YYYY-MM-DD string from extracted facts; None when missing or malformed."""
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _ref(text: str | None) -> str:
    """Normalise a bank reference for comparison: no spaces, upper case."""
    return "".join((text or "").split()).upper()


def reported_payments(state: AgentState) -> list[dict]:
    """Return distinct settlement notices in upload order, keeping corrections to the same transfer."""
    reports = {}
    for doc in parsed_docs(state, "insurer_letter"):
        facts = doc.get("facts") or {}
        if facts.get("letter_kind") != "settlement":
            continue
        report = {"source": "document", "doc_id": doc["id"], "amount": facts.get("paid_amount"),
                  "utr": facts.get("utr"), "date": facts.get("paid_on")}
        reference = _ref(report["utr"])
        # A reference identifies a transfer. When there is no reference, use both dated facts.
        if reference:
            key = ("ref", reference)
        elif report["date"] and report["amount"] is not None:
            key = ("dated", report["date"], report["amount"])
        else:
            key = ("doc", doc["id"])
        reports.pop(key, None)
        reports[key] = report
    return list(reports.values())


def reported_payment(state: AgentState) -> dict | None:
    """Return the latest settlement notice, or None when the insurer has not reported payment."""
    reports = reported_payments(state)
    return reports[-1] if reports else None


def bank_credits(state: AgentState) -> tuple[list[dict], list[tuple[date | None, date]]]:
    """Merge statements by period and keep one copy of credits repeated across uploads."""
    statements = sorted(
        parsed_docs(state, "bank_statement"),
        key=lambda doc: _day((doc.get("facts") or {}).get("statement_from")) or date.min,
    )
    credits, periods = [], []
    seen = Counter()
    for doc in statements:
        facts = doc.get("facts") or {}
        start, end = _day(facts.get("statement_from")), _day(facts.get("statement_to"))
        if end and (start is None or start <= end):
            periods.append((start, end))
        local = Counter()
        for line in facts.get("credits") or []:
            day = _day(line.get("date"))
            signature = (day, line.get("amount"), _ref(line.get("utr")) or _ref(line.get("narration")))
            local[signature] += 1
            # Preserve duplicate lines within one statement, but only the largest count across statements.
            if not day or local[signature] > seen[signature]:
                credits.append({**line, "source": "document", "doc_id": doc["id"]})
        seen |= local
    return credits, periods


def match_credits(credits: list[dict], amount: int | None, utr: str | None, after: date | None) -> tuple[list[dict], str | None]:
    """Find the bank credit(s) for one payment.

    UTR first (in the reference column or inside the narration, where banks often print it).
    Otherwise the same amount in the date window, without a conflicting printed reference.

    Returns:
        (matching credits, "utr" | "amount_and_date" | None)
    """
    key = _ref(utr)
    if key:
        by_utr = [c for c in credits if key == _ref(c.get("utr")) or key in _ref(c.get("narration"))]
        if by_utr:
            return by_utr, "utr"
    if amount is None:
        return [], None  # nothing safe to match on: never guess by date alone
    by_amount = [
        c for c in credits if c["amount"] == amount and (not key or not _ref(c.get("utr"))) and (
            after is None or (_day(c["date"]) and after <= _day(c["date"]) <= after + timedelta(CREDIT_WINDOW_DAYS)))
    ]
    return by_amount, "amount_and_date" if by_amount else None


def available_credits(credits: list[dict], earlier: list[dict]) -> list[dict]:
    """Reserve unique credits for distinct earlier transfers before matching the newest one."""
    available = credits.copy()
    for report in earlier:
        day = _day(report["date"])
        if not day and not _ref(report["utr"]):
            continue
        matches, method = match_credits(available, report["amount"], report["utr"], day)
        # A notice with its own reference cannot claim a credit through amount alone.
        if len(matches) == 1 and (method == "utr" or not _ref(report["utr"])):
            available.remove(matches[0])
    return available


def settlement_timing(info: dict, report: dict | None, today: date) -> dict | None:
    """Check the 15-day settlement rule from the user-stated submission date.

    Interest for late payment (bank rate + 2%, P-05) is only flagged, never calculated: that needs
    the current bank rate with its source and date, which Claimwise does not have.

    Returns:
        An issue when payment came, or is still missing, after the due date; else None.
    """
    submitted = _day(info.get("submitted_on"))
    if not submitted:
        return None
    due = submitted + timedelta(SETTLE_DAYS)
    paid = _day((report or {}).get("date"))
    rule = (f"due by {due.isoformat()} ({SETTLE_DAYS} days from submission on {submitted.isoformat()}, "
            "or from the last document the insurer asked for)")
    if paid and paid > due:
        return _issue("late_settlement", "warn",
            f"Paid on {paid.isoformat()}, but settlement was {rule}. Interest at bank rate + 2% may be due; "
            "Claimwise does not calculate it without the current bank rate.")
    if not paid and today > due:
        return _issue("settlement_overdue", "warn", f"No payment is recorded yet, and settlement was {rule}.")
    return None


def check_payment(state: AgentState, today: date | None = None) -> tuple[dict, list[dict]]:
    """Compare approved, reported and credited amounts for the claim.

    Args:
        state: Graph state after C1 (state["claim"] holds the decision).
        today: Override for tests; defaults to the current date.
    Returns:
        (payment summary with status, list of issues). Status is none_due (rejected), paid_to_hospital
        (cashless), awaiting (nothing reported or credited yet), reported (insurer says paid, no
        statement to check), verified, or mismatch.
    """
    decision = state["claim"]["decision"]
    info = state.get("claim_info") or {}
    reports = reported_payments(state)
    report = reports[-1] if reports else None
    approved = (decision or {}).get("approved")
    expected = report["amount"] if report and report["amount"] is not None else approved
    payment = {"approved": approved, "expected": expected, "reported": report, "credit": None, "match": None}
    issues = []

    if not decision and not report:
        return {**payment, "status": "awaiting"}, issues
    if decision and decision["outcome"] == "rejected":
        return {**payment, "status": "none_due"}, issues

    # Cashless: the insurer pays the hospital, so there is no bank credit to find. The user's share is the gap.
    if info.get("claim_type") == "cashless":
        if decision and decision["difference"]:
            issues.append(_issue("cashless_patient_share", "warn",
                f"In a cashless claim the insurer pays the hospital. Your share should be Rs {decision['difference']} "
                "(bill minus approved). Check that the hospital's final receipt matches."))
        return {**payment, "status": "paid_to_hospital"}, issues

    late = settlement_timing(info, report, today or date.today())
    issues += [late] if late else []
    if report and approved is not None and report["amount"] is not None and report["amount"] < approved:
        issues.append(_issue("short_payment", "warn",
            f"The insurer approved Rs {approved} but the settlement letter says Rs {report['amount']} was paid.",
            [report["doc_id"]]))

    credits, periods = bank_credits(state)
    after = _day((report or {}).get("date")) or _day((decision or {}).get("letter_date"))
    if not periods and not credits:
        if expected:
            issues.append(_issue("bank_statement_needed", "warn",
                f"Upload your bank statement from {after.isoformat() if after else 'the decision date'} onwards "
                "so we can check the money actually arrived. A 'settled' status alone is not proof of payment."))
        status = "reported" if report else "awaiting"
        return {**payment, "status": "mismatch" if _has(issues, "short_payment") else status}, issues

    matches, method = match_credits(available_credits(credits, reports[:-1]), expected, (report or {}).get("utr"), after)
    if method == "amount_and_date" and len(matches) > 1:
        issues.append(_issue("ambiguous_credit", "warn",
            "More than one credit matches the amount and dates. Ask the insurer for the UTR before treating the payment as verified.",
            list(dict.fromkeys(credit["doc_id"] for credit in matches))))
        return {**payment, "status": "mismatch"}, issues
    if matches:
        credit = matches[0]
        payment.update(credit=credit, match=method)
        if method == "utr" and len(matches) > 1:
            issues.append(_issue("duplicate_credit", "warn",
                f"{len(matches)} credits carry the same reference {report['utr']}. Check with your bank before using the money.",
                [c["doc_id"] for c in matches]))
        if expected is not None and credit["amount"] != expected:
            advice = f" {BANK_TRACE}" if method == "utr" else ""
            issues.append(_issue("credit_amount_mismatch", "warn",
                f"Your bank shows Rs {credit['amount']} on {credit['date']}, but Rs {expected} was expected.{advice}",
                [credit["doc_id"]]))
    elif after and periods and max(end for _, end in periods) < after:
        last_day = max(end for _, end in periods)
        issues.append(_issue("statement_too_old", "warn",
            f"Your latest statement ends on {last_day}, before the payment or decision date {after}. Upload a newer one."))
        status = "reported" if report else "awaiting"
        return {**payment, "status": "mismatch" if _has(issues, "short_payment") else status}, issues
    elif after and periods and not any(start and start <= after <= end for start, end in periods):
        issues.append(_issue("bank_statement_needed", "warn",
            f"The uploaded statement periods do not confirm coverage for {after}. Upload a statement that includes that date."))
        status = "reported" if report else "awaiting"
        return {**payment, "status": "mismatch" if _has(issues, "short_payment") else status}, issues
    elif expected:
        advice = f" {BANK_TRACE}" if report and _ref(report["utr"]) else ""
        issues.append(_issue("credit_not_found", "warn",
            f"No credit of Rs {expected}{' with reference ' + report['utr'] if report and report['utr'] else ''} "
            "is on your bank statement. 'Settled' is not proof of payment: ask the insurer for the transfer details."
            f"{advice}"))

    bad = {"short_payment", "credit_amount_mismatch", "credit_not_found", "duplicate_credit"}
    if any(i["code"] in bad for i in issues):
        status = "mismatch"
    elif matches:
        status = "verified"
    else:
        status = "reported" if report else "awaiting"
    return {**payment, "status": status}, issues


def _has(issues: list[dict], code: str) -> bool:
    """True when an issue with this code is in the list."""
    return any(i["code"] == code for i in issues)


def route_after_review(state: AgentState) -> Literal["verify_payment", "agent"]:
    """Edge after C1: check payment once the insurer has decided or says it paid, else go straight to A1."""
    return "verify_payment" if state["claim"]["decision"] or reported_payment(state) else "agent"


def verify_payment(state: AgentState) -> dict:
    """P1: add the payment check to the C1 review and move the stage on when payment is known.

    Returns:
        {"claim": C1 review + "payment", payment issues appended, stage payment_* when reported/verified/mismatch}
    """
    claim = state["claim"]
    payment, issues = check_payment(state)
    return {"claim": {
        **claim, "stage": STAGE_FOR.get(payment["status"], claim["stage"]),
        "issues": claim["issues"] + issues, "payment": payment,
    }}
