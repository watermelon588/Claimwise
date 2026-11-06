"""Deterministic decision arithmetic and clause validation for payer service."""

from typing import Any
from fastapi import HTTPException


def calculate_line_decisions(
    line_items: list[dict[str, Any]],
    room_rent_limit_per_day: int,
    days_admitted: int,
    sub_limits: list[dict[str, Any]],
    copay_percent: int,
    deductible: int,
    balance_sum_insured: int,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    """
    Compute admissible amounts per line item using standard IRDAI calculation rules:
    - Proportionate deduction on room rent and associated charges if room rent exceeds daily cap
    - Sub-limit enforcement per clinical head
    - Non-payable consumables deduction
    - Co-pay percentage deduction
    - Deductible deduction
    - Overall cap by balance sum insured
    Returns (final_approved_amount, line_decisions, deductions_clauses).
    """
    line_decisions = []
    total_admissible = 0
    clauses_cited = []

    # Check room rent proportion
    actual_room_rent_per_day = 0
    for item in line_items:
        head = item.get("head", "").lower()
        if "room" in head:
            claimed = item.get("amount", 0)
            if days_admitted > 0:
                actual_room_rent_per_day = claimed // days_admitted
            break

    room_rent_ratio = 1.0
    if room_rent_limit_per_day > 0 and actual_room_rent_per_day > room_rent_limit_per_day:
        room_rent_ratio = room_rent_limit_per_day / actual_room_rent_per_day

    # Map sub-limits by head
    sub_limit_map = {sl.get("head", "").lower(): sl.get("limit", 0) for sl in sub_limits}

    for item in line_items:
        head = item.get("head", "")
        head_lower = head.lower()
        claimed = item.get("amount", 0)
        approved = claimed
        deduction_reason = ""
        clause = ""

        # Consumables check
        if any(w in head_lower for w in ["consumable", "ppe", "sanitizer", "gloves", "mask", "administrative"]):
            approved = 0
            deduction_reason = "Non-payable consumable items excluded under policy terms"
            clause = "Clause 4.1 (Non-Payable Expenses Schedule)"
        elif "room" in head_lower and room_rent_ratio < 1.0:
            approved = int(claimed * room_rent_ratio)
            deduction_reason = f"Room rent exceeds daily limit of Rs {room_rent_limit_per_day // 100}/day"
            clause = "Clause 3.2 (Room Rent and ICU Proportionate Deduction)"
        elif any(w in head_lower for w in ["nursing", "doctor", "consultation", "surgeon"]) and room_rent_ratio < 1.0:
            approved = int(claimed * room_rent_ratio)
            deduction_reason = "Proportionate deduction applied due to room category upgrade"
            clause = "Clause 3.2 (Associated Medical Expenses Proportionate Reduction)"
        elif head_lower in sub_limit_map:
            limit = sub_limit_map[head_lower]
            if approved > limit:
                approved = limit
                deduction_reason = f"Capped by sub-limit of Rs {limit // 100}"
                clause = f"Clause 2.4 (Specific Ailment Sub-limit: {head})"

        if clause and clause not in clauses_cited:
            clauses_cited.append(clause)

        line_decisions.append({
            "head": head,
            "claimed": claimed,
            "approved": approved,
            "deduction_reason": deduction_reason,
            "policy_clause": clause
        })
        total_admissible += approved

    # Apply co-pay
    copay_deduction = 0
    if copay_percent > 0:
        copay_deduction = int(total_admissible * (copay_percent / 100.0))
        clauses_cited.append(f"Clause 5.1 ({copay_percent}% Co-Payment Mandate)")

    # Apply deductible
    deductible_deduction = min(deductible, total_admissible - copay_deduction)
    if deductible_deduction > 0:
        clauses_cited.append(f"Clause 1.3 (Deductible Amount of Rs {deductible // 100})")

    net_approved = max(0, total_admissible - copay_deduction - deductible_deduction)

    # Balance sum insured cap
    if net_approved > balance_sum_insured:
        net_approved = balance_sum_insured
        clauses_cited.append("Clause 1.1 (Sum Insured Exhaustion Cap)")

    return net_approved, line_decisions, clauses_cited


def validate_decision_clauses(outcome: str, line_decisions: list[dict[str, Any]], rejection_reason: str | None, policy_clause: str | None) -> None:
    """Ensure every deduction or rejection carries an explicit non-empty policy clause."""
    if outcome == "rejected":
        if not rejection_reason or not rejection_reason.strip():
            raise HTTPException(status_code=422, detail={"error": {"code": "CLAUSE_REQUIRED", "message": "Rejection requires an explicit reason", "retryable": False}})
        if not policy_clause or not policy_clause.strip():
            raise HTTPException(status_code=422, detail={"error": {"code": "CLAUSE_REQUIRED", "message": "Rejection requires an explicit policy clause citation", "retryable": False}})

    if outcome == "partially_approved":
        for ld in line_decisions:
            if ld.get("claimed", 0) > ld.get("approved", 0):
                clause = ld.get("policy_clause", "")
                if not clause or not clause.strip():
                    raise HTTPException(
                        status_code=422,
                        detail={"error": {"code": "CLAUSE_REQUIRED", "message": f"Deduction on line '{ld.get('head')}' requires a policy clause", "retryable": False}}
                    )
