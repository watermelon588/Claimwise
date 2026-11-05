"""Unit tests for deterministic payer decision arithmetic and clause rules."""

import pytest
from fastapi import HTTPException
from mocks.services.payer_logic import calculate_line_decisions, validate_decision_clauses


def test_room_rent_proportionate_deduction():
    """Test proportionate deduction when room rent exceeds daily cap."""
    # Policy limit: 5,000/day. Actual: 10,000/day for 2 days (total 20,000 claimed). Ratio = 0.5.
    line_items = [
        {"head": "Room Rent (2 days)", "amount": 2000000},
        {"head": "Doctor Consultation & Nursing", "amount": 1000000},
        {"head": "Pharmacy Consumables", "amount": 300000}
    ]

    net_approved, line_decisions, clauses = calculate_line_decisions(
        line_items=line_items,
        room_rent_limit_per_day=500000, # Rs 5,000 in paise
        days_admitted=2,
        sub_limits=[],
        copay_percent=0,
        deductible=0,
        balance_sum_insured=50000000
    )

    # Room rent reduced by 50% -> 10,000 (1000000 paise)
    assert line_decisions[0]["approved"] == 1000000
    # Nursing reduced by 50% -> 5,000 (500000 paise)
    assert line_decisions[1]["approved"] == 500000
    # Consumables excluded -> 0
    assert line_decisions[2]["approved"] == 0

    assert net_approved == 1500000
    assert any("Room Rent and ICU Proportionate Deduction" in c for c in clauses)


def test_copay_and_deductible():
    """Test co-pay percentage and deductible applied after admissible line decisions."""
    line_items = [
        {"head": "Surgery Charges", "amount": 10000000} # Rs 1,00,000
    ]

    # 10% copay, Rs 2,000 deductible (200000 paise)
    # Admissible = 10000000. Copay = 1000000. Deductible = 200000. Net = 8800000.
    net_approved, line_decisions, clauses = calculate_line_decisions(
        line_items=line_items,
        room_rent_limit_per_day=500000,
        days_admitted=1,
        sub_limits=[],
        copay_percent=10,
        deductible=200000,
        balance_sum_insured=50000000
    )

    assert net_approved == 8800000
    assert any("10% Co-Payment" in c for c in clauses)
    assert any("Deductible" in c for c in clauses)


def test_sub_limit_enforcement():
    """Test ailment sub-limit cap."""
    line_items = [
        {"head": "Cataract Surgery", "amount": 6000000} # 60,000
    ]
    sub_limits = [
        {"head": "Cataract Surgery", "limit": 4000000} # 40,000 cap
    ]

    net_approved, line_decisions, clauses = calculate_line_decisions(
        line_items=line_items,
        room_rent_limit_per_day=500000,
        days_admitted=1,
        sub_limits=sub_limits,
        copay_percent=0,
        deductible=0,
        balance_sum_insured=50000000
    )

    assert net_approved == 4000000
    assert line_decisions[0]["approved"] == 4000000
    assert "Clause 2.4" in line_decisions[0]["policy_clause"]


def test_clause_validation_failure():
    """Ensure rejection or deduction without clause raises 422 error."""
    with pytest.raises(HTTPException) as exc:
        validate_decision_clauses("rejected", [], "Hypertension non disclosure", "")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc2:
        validate_decision_clauses("partially_approved", [{"head": "Room", "claimed": 5000, "approved": 2000, "policy_clause": ""}], None, None)
    assert exc2.value.status_code == 422
