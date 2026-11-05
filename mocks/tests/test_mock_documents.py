"""Test suite verifying generated mock test documents and agent validation rules."""

import os
import pytest

BASE_DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mock_documents"))
VALID_DIR = os.path.join(BASE_DOCS_DIR, "valid")
INVALID_DIR = os.path.join(BASE_DOCS_DIR, "invalid")


def test_generated_pdf_files_exist_and_valid_format():
    """Verify that all 14 expected test PDFs exist and start with valid PDF headers."""
    expected_valid = [
        "01_valid_policy_schedule.pdf",
        "02_valid_discharge_summary.pdf",
        "03_valid_hospital_final_bill.pdf",
        "04_valid_bank_statement.pdf",
        "05_valid_insurer_decision_letter.pdf",
        "06_valid_insurer_query_letter.pdf"
    ]
    expected_invalid = [
        "01_flaw_name_mismatch_discharge_summary.pdf",
        "02_flaw_date_mismatch_bill.pdf",
        "03_flaw_outside_policy_period_summary.pdf",
        "04_flaw_bill_arithmetic_mismatch.pdf",
        "05_flaw_exceeds_sum_insured_bill.pdf",
        "06_flaw_repeated_renamed_query_letter.pdf",
        "07_flaw_missing_clause_decision_letter.pdf",
        "08_malicious_prompt_injection_query.pdf"
    ]

    for fname in expected_valid:
        fpath = os.path.join(VALID_DIR, fname)
        assert os.path.exists(fpath), f"Missing valid document: {fname}"
        with open(fpath, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-", f"{fname} is not a valid PDF file"
            assert os.path.getsize(fpath) > 1000, f"{fname} is too small"

    for fname in expected_invalid:
        fpath = os.path.join(INVALID_DIR, fname)
        assert os.path.exists(fpath), f"Missing invalid document: {fname}"
        with open(fpath, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-", f"{fname} is not a valid PDF file"
            assert os.path.getsize(fpath) > 1000, f"{fname} is too small"
