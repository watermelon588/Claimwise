"""Checks the demo fixtures in mock_documents/ (built by mocks.services.generate_test_suite_docs)."""

import re
import zlib
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "mock_documents"

VALID = {
    "run1_standard_reimbursement": ["01_policy_schedule", "02_discharge_summary", "03_final_bill", "04_bank_statement"],
    "run2_dispute_fallback": ["01_revised_decision_letter"],
    "run3_caregiver": ["01_policy_schedule", "02_discharge_summary", "03_final_bill", "04_consent_letter_ramesh_to_aman",
                       "05_discharge_summary_reissued_v2", "06_bank_statement_before_credit", "07_bank_statement_after_credit"],
    "run4_two_policies": ["01_policy_schedule", "02_discharge_summary", "03_final_bill", "04_policy_schedule_group_arogya",
                          "05_consent_letter_ramesh_to_aman"],
    "run5_cashless": ["01_policy_schedule", "02_discharge_summary", "03_final_bill", "04_final_bill_updated_after_tpa_payment"],
    "run6_manual_route": ["01_policy_schedule", "02_discharge_summary", "03_final_bill", "04_query_letter_hidden_instructions",
                          "05_decision_letter", "06_bank_statement_short_credit"],
    "run7_failures": ["01_policy_schedule", "02_discharge_summary", "03_final_bill"],
}
INVALID = [
    "01_discharge_summary_wrong_patient", "02_not_a_claim_document_recipe", "03_final_bill_dates_do_not_match",
    "04_discharge_summary_outside_policy_period", "05_final_bill_total_does_not_add_up", "06_final_bill_above_sum_insured",
    "07_query_letter_hidden_instructions", "08_decision_letter_without_clause", "09_query_letter_asks_again_for_discharge_summary",
    "10_consent_letter_names_someone_else", "11_consent_letter_signed_by_wrong_person", "12_consent_letter_expired",
]


def text_of(path: Path) -> str:
    """Printed text of an fpdf2 PDF: inflate each content stream and keep the (...) Tj string operands."""
    raw = path.read_bytes()
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S)
    inflated = b"".join(zlib.decompress(s) for s in streams if s[:1] == b"x")
    return " ".join(m.decode("latin-1") for m in re.findall(rb"\((.*?)\)\s*Tj", inflated))


def test_every_fixture_is_a_pdf():
    """Each file the walkthrough names exists and is a real PDF."""
    paths = [DOCS / "valid" / run / f"{name}.pdf" for run, names in VALID.items() for name in names]
    paths += [DOCS / "invalid" / f"{name}.pdf" for name in INVALID]
    for path in paths:
        assert path.exists(), f"missing {path.relative_to(DOCS)}"
        assert path.read_bytes()[:5] == b"%PDF-", f"{path.name} is not a PDF"
    assert (DOCS / "invalid" / "13_unsupported_format.txt").exists()


def test_facts_the_walkthrough_relies_on():
    """UTRs and amounts match the Mock Console values the walkthrough types; Run 4's schedule shows the revocation."""
    valid = DOCS / "valid"
    assert "UTR-DEMO-RUN1" in text_of(valid / "run1_standard_reimbursement/04_bank_statement.pdf")
    assert "Rs 44,000" in text_of(valid / "run1_standard_reimbursement/04_bank_statement.pdf")
    assert "UTR-DEMO-RUN3" not in text_of(valid / "run3_caregiver/06_bank_statement_before_credit.pdf")
    assert "UTR-DEMO-RUN3" in text_of(valid / "run3_caregiver/07_bank_statement_after_credit.pdf")
    assert "Status: revoked" in text_of(valid / "run4_two_policies/01_policy_schedule.pdf")
    assert "Status: active" in text_of(valid / "run3_caregiver/01_policy_schedule.pdf")
    assert "UTR-DEMO-RUN5-HOSPITAL" in text_of(valid / "run5_cashless/04_final_bill_updated_after_tpa_payment.pdf")
    assert "Rs 49,000" in text_of(valid / "run6_manual_route/06_bank_statement_short_credit.pdf")
    assert "Rs 53,000" in text_of(valid / "run6_manual_route/05_decision_letter.pdf")
    assert "Sita Devi" in text_of(DOCS / "invalid/01_discharge_summary_wrong_patient.pdf")
