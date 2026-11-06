"""Claim review (C1) and the submission pack: pure Python over the facts already in state.

No model calls here. Everything the agent says about amounts, dates, gaps and contradictions
comes from these functions, so it is repeatable and testable.
"""

import hashlib
import json

from app.agent.authority import actor, authority_issues
from app.agent.onboarding import same_person
from app.agent.prompts import (
    BALANCE_LINE, CHOOSE_POLICY_ISSUE, COVER_LETTER_TEMPLATE, DOC_TYPE_LABELS, REPEATED_REQUEST_ISSUE, VERSION_CHOICE_ISSUE,
)
from app.agent.state import AgentState

REQUIRED_DOCS = ("discharge_summary", "hospital_bill")
RECOMMENDED_DOCS = ("pharmacy_bill", "investigation_report", "prescription", "id_proof", "cancelled_cheque")
HOSPITAL_DOCS = {"discharge_summary", "hospital_bill", "pharmacy_bill", "investigation_report", "prescription"}
NOT_IN_PACK = {"insurer_letter", "bank_statement", "other", "policy_wording"}


def parsed_docs(state: AgentState, *doc_types: str) -> list[dict]:
    """Parsed documents in upload order, optionally only the given doc types."""
    return [
        d for d in state.get("documents", [])
        if d["status"] == "parsed" and (not doc_types or d["doc_type"] in doc_types)
    ]


def confirmed_policies(state: AgentState) -> list[dict]:
    """Every policy the user confirmed, in upload order."""
    return [p for p in state.get("policies", []) if p["status"] == "confirmed"]


def confirmed_policy(state: AgentState) -> dict | None:
    """The policy this claim goes to: the one the claimant chose (DEV-024), else the first confirmed, else None."""
    policies = confirmed_policies(state)
    chosen = (state.get("claim_info") or {}).get("policy_doc_id")
    return next((p for p in policies if p["doc_id"] == chosen), None) or (policies[0] if policies else None)


def covers(policy: dict, patient: str | None) -> bool:
    """Whether the patient is a member on the policy."""
    return bool(patient) and any(same_person(patient, m) for m in policy.get("members") or [])


def _latest_facts(state: AgentState, doc_type: str) -> dict:
    """Facts of the most recent parsed document of one type ({} if none)."""
    docs = [d for d in parsed_docs(state, doc_type) if d.get("facts")]
    return docs[-1]["facts"] if docs else {}


def _issue(code: str, severity: str, message: str, doc_ids: list[str] | None = None) -> dict:
    """One finding. severity: 'block' stops preparing the claim, 'warn' is shown but does not block."""
    return {"code": code, "severity": severity, "message": message, "doc_ids": doc_ids or []}


def build_checklist(state: AgentState) -> dict:
    """Which claim documents are present and which are still missing.

    Returns:
        {"have": [doc types], "missing_required": [...], "missing_recommended": [...]}
    """
    have = sorted({d["doc_type"] for d in parsed_docs(state)})
    return {
        "have": have,
        "missing_required": [t for t in REQUIRED_DOCS if t not in have],
        "missing_recommended": [t for t in RECOMMENDED_DOCS if t not in have],
    }


def find_issues(state: AgentState) -> list[dict]:
    """Cross-check documents against each other and against the confirmed policy.

    Checks: patient name, admission and discharge dates across documents, treatment inside the
    policy period, bill lines adding up to the total, total within sum insured, unreadable files.
    """
    issues = []
    policy = confirmed_policy(state)
    role = state.get("user_role")
    patient = role["patient_name"] if role else None
    hospital_docs = [d for d in parsed_docs(state, *HOSPITAL_DOCS) if d.get("facts")]

    # Every hospital document must be about the same patient.
    for d in hospital_docs:
        name = d["facts"].get("patient_name")
        if patient and name and not same_person(patient, name):
            issues.append(_issue("name_mismatch", "block",
                f"{d['filename']} names the patient '{name}', but the patient is '{patient}'.", [d["id"]]))

    # Admission and discharge dates must agree across documents.
    for field in ("admission_date", "discharge_date"):
        values = {d["facts"][field]: d for d in hospital_docs if d["facts"].get(field)}
        if len(values) > 1:
            label = field.replace("_", " ")
            issues.append(_issue("date_mismatch", "block",
                f"Documents disagree on the {label}: {', '.join(sorted(values))}.", [d["id"] for d in values.values()]))

    # Treatment should fall inside the policy period (ISO dates compare correctly as strings).
    start, end = (policy or {}).get("period_start"), (policy or {}).get("period_end")
    admissions = {d["facts"]["admission_date"] for d in hospital_docs if d["facts"].get("admission_date")}
    for day in sorted(admissions):
        if start and end and not start <= day <= end:
            issues.append(_issue("outside_policy_period", "warn",
                f"Admission on {day} is outside the policy period {start} to {end}."))

    # Bill arithmetic and sum insured.
    for d in parsed_docs(state, "hospital_bill"):
        facts = d.get("facts") or {}
        total, lines = facts.get("total_amount"), facts.get("line_items") or []
        line_sum = sum(item["amount"] for item in lines)
        if total is not None and lines and line_sum != total:
            issues.append(_issue("bill_total_mismatch", "warn",
                f"{d['filename']}: bill lines add up to Rs {line_sum}, but the total says Rs {total}.", [d["id"]]))
        sum_insured = (policy or {}).get("sum_insured")
        if total is not None and sum_insured is not None and total > sum_insured:
            issues.append(_issue("over_sum_insured", "warn",
                f"Bill total Rs {total} is more than the sum insured Rs {sum_insured}.", [d["id"]]))

    for d in state.get("documents", []):
        if d["status"] == "failed":
            issues.append(_issue("unreadable_document", "warn", f"Could not read {d['filename']}.", [d["id"]]))

    # DEV-023: a second document of the same type waits for "replace or keep both" before the pack.
    by_id = {d["id"]: d for d in state.get("documents", [])}
    for d in parsed_docs(state):
        if d.get("version_choice") == "pending" and d.get("version_of") in by_id:
            issues.append(_issue("version_choice", "block", VERSION_CHOICE_ISSUE.format(
                new=d["filename"], old=by_id[d["version_of"]]["filename"]), [d["id"], d["version_of"]]))
    # DEV-024: with several policies covering the patient, the claimant chooses where to claim first.
    eligible = [p for p in confirmed_policies(state) if covers(p, patient)]
    if len(eligible) > 1 and not (state.get("claim_info") or {}).get("policy_doc_id"):
        issues.append(_issue("choose_policy", "block", CHOOSE_POLICY_ISSUE.format(count=len(eligible))))
    # DEV-025: a caregiver's authority must be current and cover submission.
    issues += [_issue(code, "block", message) for code, message in authority_issues(state)]
    return issues


def _latest_letter(state: AgentState) -> dict | None:
    """Most recent insurer letter with facts, or None."""
    letters = [d for d in parsed_docs(state, "insurer_letter") if d.get("facts")]
    return letters[-1] if letters else None


def read_decision(state: AgentState) -> dict | None:
    """Compare the latest decision letter with what was claimed, line by line.

    Returns:
        None if no letter decides the claim; else outcome, claimed, approved,
        difference, per-line deductions and the lines with a deduction but no clause cited.
    """
    # The latest deciding letter, not just the latest letter: a later settlement advice must not hide
    # the decision. A settlement letter that states an outcome counts as the decision when none came before.
    letters = [d for d in parsed_docs(state, "insurer_letter") if d.get("facts")]
    decisions = [d for d in letters if d["facts"].get("letter_kind") == "decision"]
    settled = [d for d in letters if d["facts"].get("letter_kind") == "settlement" and d["facts"].get("outcome")]
    letter = (decisions or settled or [None])[-1]
    if not letter:
        return None
    f = letter["facts"]
    claimed = f.get("claimed_amount") or _latest_facts(state, "hospital_bill").get("total_amount")
    approved = f.get("approved_amount")
    lines = []
    for line in f.get("line_decisions") or []:
        both = line.get("claimed") is not None and line.get("approved") is not None
        lines.append({**line, "deducted": line["claimed"] - line["approved"] if both else None})
    missing_clause = [l["head"] for l in lines if (l["deducted"] or 0) > 0 and not l.get("clause")]
    if f.get("outcome") == "rejected" and not f.get("clause"):
        missing_clause.append("whole claim (rejection)")
    return {
        "letter_doc_id": letter["id"], "letter_date": f.get("letter_date"), "outcome": f.get("outcome"),
        "claimed": claimed, "approved": approved,
        "difference": claimed - approved if claimed is not None and approved is not None else None,
        "lines": lines, "reason": f.get("reason"), "clause": f.get("clause"), "missing_clause": missing_clause,
    }


def read_query(state: AgentState) -> dict | None:
    """Read the latest query letter and mark requested items that were already provided.

    Returns:
        None if the latest insurer letter is not a query, or it is marked answered (by the insurer through
        the connector, or by the user); else the requested items, each with already_provided = filename of
        a document of the same type given before the query arrived, or None.
    """
    letter = _latest_letter(state)
    if not letter or letter["facts"].get("letter_kind") != "query" or letter["facts"].get("query_status") == "answered":
        return None
    # Only documents Claimwise had before the query count as "already sent"; later uploads answer it.
    seen = letter.get("uploaded_at")
    provided = {d["doc_type"]: d for d in parsed_docs(state) if d["id"] != letter["id"]
                and not (seen and d.get("uploaded_at") and d["uploaded_at"] >= seen)}
    requested = [
        {**item, "already_provided": (provided.get(item["doc_type"]) or {}).get("filename"),
         "provided_on": ((provided.get(item["doc_type"]) or {}).get("uploaded_at") or "")[:10] or None}
        for item in letter["facts"].get("requested_documents") or []
    ]
    return {"letter_doc_id": letter["id"], "letter_date": letter["facts"].get("letter_date"), "requested": requested}


def build_submission_pack(state: AgentState) -> dict:
    """Assemble the claim pack and a deterministic cover letter from confirmed and extracted facts.

    Returns:
        Pack fields, the document list, the cover letter, and a hash of the content (used to
        detect when an approval no longer matches the documents).
    """
    policy = confirmed_policy(state) or {}
    role = state.get("user_role") or {}
    info = state.get("claim_info") or {}
    summary, bill = _latest_facts(state, "discharge_summary"), _latest_facts(state, "hospital_bill")
    balance = info.get("balance_of") or None
    pack = {
        "claim_type": info.get("claim_type"),
        "patient": role.get("patient_name"),
        "insurer": policy.get("insurer"),
        "policy_number": policy.get("policy_number"),
        "tpa": policy.get("tpa"),
        "hospital": summary.get("hospital_name") or bill.get("hospital_name"),
        "admission_date": summary.get("admission_date") or bill.get("admission_date"),
        "discharge_date": summary.get("discharge_date") or bill.get("discharge_date"),
        "claimed_amount": balance["balance"] if balance else bill.get("total_amount"),
        "documents": [
            {"id": d["id"], "filename": d["filename"], "doc_type": d["doc_type"]}
            for d in parsed_docs(state) if d["doc_type"] not in NOT_IN_PACK
        ] + [
            # A balance claim encloses the earlier insurer's decision and settlement letters (research P-11, C-02).
            {"id": d["id"], "filename": d["filename"], "doc_type": d["doc_type"]}
            for d in state.get("documents", []) if balance and d["status"] == "archived"
            and (d.get("facts") or {}).get("letter_kind") in ("decision", "settlement")
        ],
    }
    pack["hash"] = hashlib.sha256(json.dumps(pack, sort_keys=True, default=str).encode()).hexdigest()[:16]
    by = actor(state)
    pack["cover_letter"] = COVER_LETTER_TEMPLATE.format(
        insurer=pack["insurer"] or "the insurer",
        tpa_line=f" (through {pack['tpa']})" if pack["tpa"] else "",
        claim_type_label=pack["claim_type"] or "health insurance",
        patient=pack["patient"], policy_number=pack["policy_number"], hospital=pack["hospital"] or "not stated",
        admission_date=pack["admission_date"] or "not stated", discharge_date=pack["discharge_date"] or "not stated",
        claimed_amount=pack["claimed_amount"] if pack["claimed_amount"] is not None else "not stated",
        document_lines="\n".join(
            f"- {DOC_TYPE_LABELS.get(d['doc_type'], d['doc_type'].replace('_', ' '))}: {d['filename']}"
            for d in pack["documents"]
        ),
        submitted_by=by,
        balance_line=BALANCE_LINE.format(**balance) if balance else "",
    )
    return pack


def submission_blockers(state: AgentState) -> list[str]:
    """Reasons the pack cannot be prepared yet (empty list means it can)."""
    review = state.get("claim") or review_claim(state)["claim"]
    blockers = []
    if not (state.get("onboarding") or {}).get("complete"):
        blockers.append("onboarding is not complete")
    if not (state.get("claim_info") or {}).get("claim_type"):
        blockers.append("claim type (cashless or reimbursement) is not known")
    blockers += [f"missing {DOC_TYPE_LABELS[t]}" for t in review["checklist"]["missing_required"]]
    blockers += [i["message"] for i in review["issues"] if i["severity"] == "block"]
    return blockers


def review_claim(state: AgentState) -> dict:
    """C1: recompute the whole claim review from state, every turn.

    Stage is derived, never stored by hand: decided / query_raised from the latest insurer letter,
    submitted from the user-stated date, approved_to_submit when the approval still matches the
    current pack, otherwise preparing. An approval whose pack changed is flagged as invalidated.

    Returns:
        {"claim": {stage, checklist, issues, query, decision, pack_hash}}
    """
    info = state.get("claim_info") or {}
    decision, query = read_decision(state), read_query(state)
    issues = find_issues(state)
    pack_hash = build_submission_pack(state)["hash"]
    approval = state.get("submission_approval")
    approval_valid = bool(approval) and approval["hash"] == pack_hash

    if approval and not approval_valid and not info.get("submitted_on"):
        issues.append(_issue("approval_invalidated", "warn",
            "Documents changed after you approved the claim pack. Please review and approve it again."))
    if decision and decision["missing_clause"]:
        issues.append(_issue("clause_not_cited", "warn",
            "The decision does not cite a policy clause for: " + ", ".join(decision["missing_clause"]) + ".",
            [decision["letter_doc_id"]]))
    for item in (query or {}).get("requested", []):
        if item["already_provided"]:
            issues.append(_issue("repeated_request", "warn", REPEATED_REQUEST_ISSUE.format(
                label=item["label"], date=item["provided_on"] or "earlier", filename=item["already_provided"]),
                [query["letter_doc_id"]]))

    if decision:
        stage = "decided"
    elif query:
        stage = "query_raised"
    elif info.get("submitted_on"):
        stage = "submitted"
    elif approval_valid:
        stage = "approved_to_submit"
    else:
        stage = "preparing"
    return {"claim": {
        "stage": stage, "checklist": build_checklist(state), "issues": issues,
        "query": query, "decision": decision, "pack_hash": pack_hash,
    }}
