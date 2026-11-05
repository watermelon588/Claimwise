"""Scenario presets and database seed routines for deterministic test cases."""

import json
import sqlite3
import uuid
from mocks.clock import get_current_time_iso, set_time
from mocks.db import get_connection, init_db
from mocks.faults import set_faults, FaultsModel


def seed_base_entities(conn: sqlite3.Connection) -> None:
    """Seed baseline fictional entities: hospitals, policies, bank accounts."""
    now = get_current_time_iso(conn)

    # 1. Base Hospital: Sunrise Hospital (MOCK)
    conn.execute("""
    INSERT OR REPLACE INTO hospitals (id, name, city, network_insurers)
    VALUES (?, ?, ?, ?);
    """, (
        "HOSP-001",
        "Sunrise Hospital (MOCK)",
        "New Delhi",
        json.dumps(["Suraksha General Insurance (MOCK)", "Arogya Shield (MOCK)"])
    ))

    # 2. Base Bank Account: Bharat Demo Bank
    conn.execute("""
    INSERT OR REPLACE INTO bank_accounts (id, holder_name, account_last4, ifsc)
    VALUES (?, ?, ?, ?);
    """, (
        "ACC-001",
        "Ramesh Sharma",
        "8921",
        "BDBK0001234"
    ))

    # 3. Base Policy: Suraksha Gold Health
    conn.execute("""
    INSERT OR REPLACE INTO policies (
        id, policy_number, insurer_name, tpa_name, policy_type,
        period_start, period_end, sum_insured, balance_sum_insured,
        room_rent_limit_per_day, copay_percent, deductible,
        waiting_periods, exclusions, sub_limits, members,
        authorised_representatives, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
    """, (
        "POL-001",
        "SURAKSHA-HEALTH-2026-001",
        "Suraksha General Insurance (MOCK)",
        "Medivista TPA (MOCK)",
        "family_floater",
        "2026-01-01",
        "2026-12-31",
        50000000, # Rs 5,00,000 in paise
        50000000,
        500000,   # Rs 5,000/day
        10,       # 10% co-pay
        100000,   # Rs 1,000 deductible
        json.dumps([{"condition": "Pre-Existing Diseases", "months": 24}]),
        json.dumps(["Cosmetic surgery", "Non-prescription vitamins"]),
        json.dumps([{"head": "Cataract", "limit": 4000000}]), # Rs 40,000 cap
        json.dumps([
            {"member_id": "MEM-01", "name": "Ramesh Sharma", "relation": "Primary", "dob": "1975-06-15"},
            {"member_id": "MEM-02", "name": "Sunita Sharma", "relation": "Spouse", "dob": "1978-08-20"},
            {"member_id": "MEM-03", "name": "Aman Sharma", "relation": "Son", "dob": "2005-02-10"}
        ]),
        json.dumps([
            {"name": "Aman Sharma", "relation": "Son", "status": "active"}
        ]),
        now
    ))


def reset_database() -> None:
    """Clear all tables and re-initialize with base seed records."""
    conn = get_connection()
    try:
        # Drop all application tables
        tables = [
            "ombudsman_complaints", "grievances", "bank_credits", "bank_accounts",
            "hospital_documents", "admissions", "hospitals", "payments",
            "decisions", "queries", "claims", "preauths", "policies",
            "events", "idempotency", "faults", "clock"
        ]
        for t in tables:
            conn.execute(f"DROP TABLE IF EXISTS {t};")
        conn.commit()

        # Re-create schema and seed
        init_db(conn)
        seed_base_entities(conn)
        conn.commit()
    finally:
        conn.close()


def load_scenario(scenario_name: str) -> dict:
    """Reset database and apply a pre-configured test scenario."""
    reset_database()
    conn = get_connection()
    try:
        now = get_current_time_iso(conn)

        if scenario_name == "standard_reimbursement":
            # Retail individual policy, discharge done, claim approved in full, credit matches
            conn.execute("""
            INSERT OR REPLACE INTO admissions (
                id, hospital_id, patient_name, policy_number, admission_date, discharge_date,
                diagnosis_text, status, deposit_amount, deposit_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                "ADM-001", "HOSP-001", "Ramesh Sharma", "SURAKSHA-HEALTH-2026-001",
                "2026-10-02", "2026-10-05", "Acute Appendicitis", "discharged", 0, "released"
            ))
            # Claim submitted
            line_items = [
                {"head": "Room Rent & Nursing (3 days)", "amount": 1200000}, # 12,000 (4,000/day <= 5,000/day limit)
                {"head": "Operation Theatre & Surgeon Charges", "amount": 3500000},
                {"head": "Medicines & Investigations", "amount": 1300000}
            ]
            conn.execute("""
            INSERT OR REPLACE INTO claims (
                id, client_reference, policy_id, member_id, claim_type, admission_date, discharge_date,
                claimed_amount, line_items, documents, submitted_at, status, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
            """, (
                "CLM-0001", "CLIENT-REF-001", "POL-001", "MEM-01", "reimbursement",
                "2026-10-02", "2026-10-05", 6000000, json.dumps(line_items), json.dumps([]),
                "2026-10-06T10:00:00+05:30", "submitted", now
            ))
            conn.commit()
            return {"scenario": scenario_name, "claim_id": "CLM-0001", "description": "Standard reimbursement claim ready for approval"}

        elif scenario_name == "repeated_renamed_request":
            # Claim in query_raised state with a deficiency request for discharge summary
            conn.execute("""
            INSERT OR REPLACE INTO claims (
                id, client_reference, policy_id, member_id, claim_type, admission_date, discharge_date,
                claimed_amount, line_items, documents, submitted_at, status, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2, ?);
            """, (
                "CLM-0002", "CLIENT-REF-002", "POL-001", "MEM-01", "reimbursement",
                "2026-10-02", "2026-10-05", 5000000, "[]", "[]",
                "2026-10-06T10:00:00+05:30", "query_raised", now
            ))
            conn.execute("""
            INSERT OR REPLACE INTO queries (id, claim_id, raised_at, due_at, items, status)
            VALUES (?, ?, ?, ?, ?, 'open');
            """, (
                "QRY-001", "CLM-0002", "2026-10-08T11:00:00+05:30", "2026-10-23T11:00:00+05:30",
                json.dumps([{"code": "DOC_DISCHARGE_SUMMARY", "label": "Discharge summary", "description": "Hospital discharge summary signed by treating doctor."}])
            ))
            conn.commit()
            return {"scenario": scenario_name, "claim_id": "CLM-0002", "query_id": "QRY-001", "description": "First deficiency request open"}

        elif scenario_name == "partial_with_mismatched_credit":
            # Partial approval Rs 42,300; bank credit Rs 38,300 with different UTR
            conn.execute("""
            INSERT OR REPLACE INTO claims (
                id, client_reference, policy_id, member_id, claim_type, admission_date, discharge_date,
                claimed_amount, line_items, documents, submitted_at, status, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, ?);
            """, (
                "CLM-0003", "CLIENT-REF-003", "POL-001", "MEM-01", "reimbursement",
                "2026-10-02", "2026-10-05", 5500000, "[]", "[]",
                "2026-10-06T10:00:00+05:30", "payment_advised", now
            ))
            conn.execute("""
            INSERT OR REPLACE INTO decisions (
                id, claim_id, outcome, decided_at, approved_amount, line_decisions, policy_clause
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                "DEC-0003", "CLM-0003", "partially_approved", "2026-10-12T14:00:00+05:30",
                4230000, json.dumps([{"head": "Adjudicated net", "claimed": 5500000, "approved": 4230000, "policy_clause": "Clause 3.2 (Room Rent Cap)"}]),
                "Clause 3.2 (Room Rent Cap)"
            ))
            conn.execute("""
            INSERT OR REPLACE INTO payments (
                id, claim_id, amount, utr, paid_at, payee, bank_account_last4
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                "PAY-0003", "CLM-0003", 4230000, "UTR-INSURER-42300", "2026-10-13T10:00:00+05:30", "member", "8921"
            ))
            # Mismatched credit in bank
            conn.execute("""
            INSERT OR REPLACE INTO bank_credits (
                id, account_id, amount, utr, credited_at, narration
            ) VALUES (?, ?, ?, ?, ?, ?);
            """, (
                "CR-0003", "ACC-001", 3830000, "UTR-BANK-38300-DIFF", "2026-10-14T11:30:00+05:30", "CMS/SURAKSHA/CLM3-SHORT"
            ))
            conn.commit()
            return {"scenario": scenario_name, "claim_id": "CLM-0003", "approved": 4230000, "bank_credit": 3830000}

        elif scenario_name == "rejection_to_ombudsman":
            # Claim rejected citing non-disclosure, grievance rejected, ready for ombudsman
            conn.execute("""
            INSERT OR REPLACE INTO claims (
                id, client_reference, policy_id, member_id, claim_type, admission_date, discharge_date,
                claimed_amount, line_items, documents, submitted_at, status, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, ?);
            """, (
                "CLM-0004", "CLIENT-REF-004", "POL-001", "MEM-01", "reimbursement",
                "2026-09-01", "2026-09-04", 8000000, "[]", "[]",
                "2026-09-05T10:00:00+05:30", "rejected", now
            ))
            conn.execute("""
            INSERT OR REPLACE INTO decisions (
                id, claim_id, outcome, decided_at, approved_amount, rejection_reason, policy_clause
            ) VALUES (?, ?, ?, ?, 0, ?, ?);
            """, (
                "DEC-0004", "CLM-0004", "rejected", "2026-09-10T12:00:00+05:30",
                "Repudiated on grounds of alleged non-disclosure of hypertension.", "Clause 6.1 (Disclosure to Information Norm)"
            ))
            conn.execute("""
            INSERT OR REPLACE INTO grievances (
                id, level, claim_id, filed_at, acknowledged_at, due_at, status, resolution_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                "GRV-0001", "insurer_gro", "CLM-0004", "2026-09-12T10:00:00+05:30", "2026-09-12T10:05:00+05:30",
                "2026-09-26T10:00:00+05:30", "resolved", "Grievance rejected upon internal review. Repudiation upheld under Clause 6.1."
            ))
            conn.commit()
            return {"scenario": scenario_name, "claim_id": "CLM-0004", "grievance_id": "GRV-0001", "description": "Grievance repudiated; eligible for Insurance Ombudsman filing"}

        elif scenario_name == "lost_submit_response":
            # Enable drop_response_after_commit fault
            set_faults(FaultsModel(drop_response_after_commit=True), conn)
            conn.commit()
            return {"scenario": scenario_name, "fault": "drop_response_after_commit enabled"}

        elif scenario_name == "caregiver_consent_change_two_policies":
            # Second policy: Group health policy from Employer
            conn.execute("""
            INSERT OR REPLACE INTO policies (
                id, policy_number, insurer_name, tpa_name, policy_type,
                period_start, period_end, sum_insured, balance_sum_insured,
                room_rent_limit_per_day, copay_percent, deductible,
                waiting_periods, exclusions, sub_limits, members,
                authorised_representatives, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
            """, (
                "POL-002",
                "CORP-GROUP-HEALTH-2026-88",
                "Arogya Shield (MOCK)",
                "HealthIndia TPA (MOCK)",
                "group",
                "2026-04-01",
                "2027-03-31",
                30000000, # Rs 3,00,000
                30000000,
                0,        # No room rent cap
                0,        # 0% co-pay
                0,        # 0 deductible
                "[]", "[]", "[]",
                json.dumps([{"member_id": "MEM-01", "name": "Ramesh Sharma", "relation": "Employee", "dob": "1975-06-15"}]),
                "[]",
                now
            ))
            # Revoke caregiver on POL-001
            conn.execute("""
            UPDATE policies SET authorised_representatives = ? WHERE id = 'POL-001';
            """, (json.dumps([{"name": "Aman Sharma", "relation": "Son", "status": "revoked"}]),))
            conn.commit()
            return {"scenario": scenario_name, "second_policy_id": "POL-002", "caregiver_status": "revoked"}

        else:
            conn.commit()
            return {"scenario": scenario_name, "status": "base entities seeded"}
    finally:
        conn.close()
