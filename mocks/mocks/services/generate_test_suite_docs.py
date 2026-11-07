"""Build the synthetic PDF fixtures used by the demo walkthrough (docs/07-delivery/demo-walkthrough.md).

valid/ holds one folder per walkthrough run. Its PDFs come from the real mock services, driven in-process
through the same steps the walkthrough performs in the Mock Console, so each file matches what the console
would generate. Settlements use fixed UTRs (`utr_override`), so a static bank statement matches the live
payment when the walkthrough sends the same UTR. Documents the mock cannot produce (consent letters, the
cashless bill updated after the TPA pays the hospital) use the mock's own PDF style.

invalid/ holds flawed, hostile or unrelated files for the checks in Runs 1, 3, 5 and 7.

Run from mocks/:  uv run python -m mocks.services.generate_test_suite_docs
The generator uses a temporary database and document folder, turns webhooks off, and never touches
mock.db or a running backend. A seeded uuid makes the IDs stable between regenerations.
"""

import os
import random
import shutil
import tempfile
import uuid

from mocks.config import settings
from mocks.services.pdf_generator import (
    MockDocumentPDF,
    generate_decision_letter_pdf,
    generate_discharge_summary_pdf,
    generate_final_bill_pdf,
    generate_query_letter_pdf,
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mock_documents"))
VALID_DIR, INVALID_DIR = os.path.join(BASE_DIR, "valid"), os.path.join(BASE_DIR, "invalid")

# Fixed values the walkthrough types into the Mock Console so live payments match these statements.
UTR = {"run1": "UTR-DEMO-RUN1", "run3": "UTR-DEMO-RUN3", "run5": "UTR-DEMO-RUN5-HOSPITAL", "run6": "UTR-DEMO-RUN6"}
HOSPITAL_KEY = {"X-Api-Key": "hospital-demo-key"}
CLAIMWISE_KEY = {"X-Api-Key": "claimwise-demo-key"}
HOSPITAL = {"name": "Sunrise Hospital (MOCK)", "city": "New Delhi"}
BILL_LINES = [  # The mock hospital's discharge bill (mocks/routers/hospital.py), amounts in paise.
    {"head": "Room & Nursing Charges", "amount": 1500000},
    {"head": "Operation Theatre & Surgeon Charges", "amount": 3500000},
    {"head": "Pharmacy & Consumables", "amount": 1000000},
]


class Mock:
    """The mock services in-process, with the request bodies the Mock Console prefills."""

    def __init__(self, work: str):
        """Point the mock at a private database and document folder, then open a test client."""
        from fastapi.testclient import TestClient
        from mocks.main import app

        settings.mock_db_path = os.path.join(work, "mock.db")
        settings.docs_storage_path = os.path.join(work, "docs")
        self.client = TestClient(app)

    def call(self, method: str, path: str, **kwargs) -> dict:
        """One request; any non-2xx response stops generation with its body."""
        response = self.client.request(method, path, **kwargs)
        assert response.is_success, f"{method} {path}: {response.status_code} {response.text}"
        return response.json() if "json" in response.headers.get("content-type", "") else {}

    def pdf(self, path: str, target: str) -> None:
        """Download a generated PDF to the fixture folder."""
        response = self.client.get(path)
        assert response.is_success and response.content[:5] == b"%PDF-", f"{path}: {response.status_code}"
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(response.content)

    def start(self, scenario: str | None = None) -> None:
        """Reset (or load a scenario) and switch webhooks off so nothing reaches a running backend."""
        self.call("POST", f"/admin/scenarios/{scenario}" if scenario else "/admin/reset")
        self.call("POST", "/admin/faults", json={"webhook_down": True})
        # The mock caches a policy schedule PDF on first download and a reset does not clear it,
        # so drop cached schedules to make each run's schedule show that run's data (Run 4: Aman revoked).
        storage = settings.docs_storage_path
        for name in os.listdir(storage) if os.path.isdir(storage) else []:
            if name.startswith("DOC-POL-"):
                os.remove(os.path.join(storage, name))

    def admit_and_discharge(self) -> dict:
        """Mock Console: Hospital, Admit patient; then Discharge summary & final bill (5 October)."""
        admission = self.call("POST", "/hospital/admissions", headers=HOSPITAL_KEY, json={
            "hospital_id": "HOSP-001", "patient_name": "Ramesh Sharma", "policy_number": "SURAKSHA-HEALTH-2026-001",
            "admission_date": "2026-10-02", "diagnosis_text": "Acute Appendicitis (Laparoscopic Appendectomy)",
            "deposit_amount": 1000000})
        admission_id = admission["admission_id"]
        return self.call("POST", f"/hospital/admissions/{admission_id}/discharge?discharge_date=2026-10-05",
                         headers=HOSPITAL_KEY)

    def hospital_set(self, folder: str, discharge: dict, policy: str = "SURAKSHA-HEALTH-2026-001") -> None:
        """Download the policy schedule, discharge summary and final bill into a run folder."""
        self.pdf(f"/payer/documents/DOC-POL-{policy}.pdf", os.path.join(folder, "01_policy_schedule.pdf"))
        self.pdf(f"/hospital/documents/{discharge['discharge_summary_doc_id']}.pdf", os.path.join(folder, "02_discharge_summary.pdf"))
        self.pdf(f"/hospital/documents/{discharge['final_bill_doc_id']}.pdf", os.path.join(folder, "03_final_bill.pdf"))

    def submit(self, reference: str, claim_type: str = "reimbursement", acting_user: str | None = None,
               policy: str = "SURAKSHA-HEALTH-2026-001") -> str:
        """The claim Claimwise submits through the TPA (Submit for me): the bill's three lines."""
        body = {"client_reference": reference, "policy_number": policy, "member_name": "Ramesh Sharma",
                "acting_user": acting_user, "claim_type": claim_type, "admission_date": "2026-10-02",
                "discharge_date": "2026-10-05", "claimed_amount": 6000000, "line_items": BILL_LINES,
                "documents": [{"doc_type": "discharge_summary", "filename": "02_discharge_summary.pdf"},
                              {"doc_type": "hospital_bill", "filename": "03_final_bill.pdf"}]}
        headers = {**CLAIMWISE_KEY, "Idempotency-Key": f"idem-{reference}"}
        return self.call("POST", "/payer/claims", headers=headers, json=body)["id"]

    def decide(self, claim_id: str, outcome: str, line_decisions: list | None = None) -> dict:
        """Mock Console: Insurer, Decide claim."""
        return self.call("POST", f"/payer/claims/{claim_id}/decide", json={
            "outcome": outcome, "rejection_reason": None, "policy_clause": None, "line_decisions": line_decisions})

    def clock(self, days: int) -> None:
        """Mock Console: Test controls, Clock."""
        self.call("POST", "/admin/clock/advance", json={"days": days, "hours": 0, "minutes": 0})


def letter(path: str, title: str, rows: list[str], table: list[tuple[str, int]] | None = None,
           total_label: str = "", printed_total: int | None = None, notes: list[str] | None = None) -> None:
    """A document in the mock's PDF style: key lines, an optional amount table, then free text.

    Args:
        rows: "Label: value" lines printed first.
        table: (head, paise) rows; the total row prints printed_total when given, else the real sum.
        notes: paragraphs printed after the table.
    """
    pdf = MockDocumentPDF(title)
    pdf.add_page()
    pdf.set_font("helvetica", "", 10)
    for row in rows:
        pdf.cell(0, 6, row, new_x="LMARGIN", new_y="NEXT")
    if table:
        pdf.ln(4)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(120, 7, "Expense Head / Description", border=1)
        pdf.cell(60, 7, "Amount (INR)", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9)
        for head, amount in table:
            pdf.cell(120, 6, head, border=1)
            pdf.cell(60, 6, f"Rs {amount // 100:,}", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
        total = printed_total if printed_total is not None else sum(a for _, a in table)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(120, 7, total_label, border=1)
        pdf.cell(60, 7, f"Rs {total // 100:,}", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
    for note in notes or []:
        pdf.ln(3)
        pdf.set_font("helvetica", "", 9)
        pdf.multi_cell(0, 5, note)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pdf.output(path)


def consent_letter(path: str, representative: str = "Aman Sharma", grantor: str = "Ramesh Sharma",
                   valid_until: str = "2027-06-30") -> None:
    """Patient's written consent for a family member to act on the claim (Runs 3 and 4)."""
    letter(path, "CONSENT AND AUTHORISATION LETTER (MOCK)", [
        "Date: 2026-10-01",
        "Policy Number: SURAKSHA-HEALTH-2026-001",
        "Insurer: Suraksha General Insurance (MOCK) | TPA: Medivista TPA (MOCK)",
        f"Grantor (patient and policy member): {grantor}",
        f"Authorised representative: {representative}",
        f"Valid until: {valid_until}",
    ], notes=[
        f"I, {grantor}, member of the health policy SURAKSHA-HEALTH-2026-001, authorise {representative} to "
        "submit and follow up my hospitalisation claims, share my medical records with the insurer and its TPA, "
        "receive updates, and file grievances on my behalf.",
        f"This authority is valid until {valid_until}.",
        f"Signed: {grantor}",
    ])


def build_valid(mock: Mock) -> None:
    """Run the walkthrough's mock steps and keep every PDF a run uploads."""
    folder = lambda name: os.path.join(VALID_DIR, name)  # noqa: E731

    # Run 1: standard reimbursement, partial decision, settlement to the member with a fixed UTR.
    run1 = folder("run1_standard_reimbursement")
    mock.start()
    mock.hospital_set(run1, mock.admit_and_discharge())
    claim = mock.submit("demo-run1-claim")
    mock.clock(6)
    mock.decide(claim, "partially_approved")
    mock.call("POST", f"/payer/claims/{claim}/pay", json={"payee": "member", "utr_override": UTR["run1"]})
    mock.pdf("/bank/accounts/ACC-001/statement.pdf", os.path.join(run1, "04_bank_statement.pdf"))

    # Run 2 (same world): Ombudsman award reopens the claim; the insurer approves every line.
    run2 = folder("run2_dispute_fallback")
    grievance = mock.call("POST", "/grievance/grievances", headers=CLAIMWISE_KEY, json={
        "claim_id": claim, "level": "insurer_gro", "complaint_text": "Disputing the consumables deduction."})
    mock.clock(31)
    complaint = mock.call("POST", "/grievance/ombudsman", headers=CLAIMWISE_KEY, json={
        "grievance_id": grievance["grievance_id"], "claim_id": claim,
        "complaint_summary": "Consumables deducted without a valid exclusion."})
    mock.call("POST", f"/grievance/ombudsman/{complaint['ombudsman_id']}/award", json={
        "award_amount": 1600000, "award_notes": "Insurer to reconsider the consumables.", "reopen_claim": True})
    full = [{"head": l["head"], "claimed": l["amount"], "approved": l["amount"]} for l in BILL_LINES]
    revised = mock.decide(claim, "approved", full)
    mock.pdf(f"/payer/documents/{revised['letter_doc_id']}.pdf", os.path.join(run2, "01_revised_decision_letter.pdf"))

    # Run 3: caregiver; reissued summary v2; settlement without a credit, then the credit arrives late.
    run3 = folder("run3_caregiver")
    mock.start()
    discharge = mock.admit_and_discharge()
    mock.hospital_set(run3, discharge)
    consent_letter(os.path.join(run3, "04_consent_letter_ramesh_to_aman.pdf"))
    reissued = mock.call("POST", f"/hospital/documents/{discharge['discharge_summary_doc_id']}/reissue", json={
        "corrected_diagnosis": "Acute Appendicitis (Symptom duration 48 hours, no prior history)",
        "corrected_line_items": None})
    mock.pdf(f"/hospital/documents/{reissued['reissued_doc_id']}.pdf", os.path.join(run3, "05_discharge_summary_reissued_v2.pdf"))
    claim = mock.submit("demo-run3-claim", acting_user="Aman Sharma")
    mock.clock(6)
    approved = mock.decide(claim, "approved")
    mock.call("POST", f"/payer/claims/{claim}/pay", json={"payee": "member", "utr_override": UTR["run3"], "skip_credit": True})
    mock.pdf("/bank/accounts/ACC-001/statement.pdf", os.path.join(run3, "06_bank_statement_before_credit.pdf"))
    mock.call("POST", "/bank/accounts/ACC-001/credits", headers=CLAIMWISE_KEY, json={
        "amount": approved["approved_amount"], "utr": UTR["run3"], "narration": f"NEFT/SURAKSHA/{claim}", "credited_at": None})
    mock.pdf("/bank/accounts/ACC-001/statement.pdf", os.path.join(run3, "07_bank_statement_after_credit.pdf"))

    # Run 4: the scenario revokes Aman at the insurer and adds Ramesh's group policy.
    run4 = folder("run4_two_policies")
    mock.start("caregiver_consent_change_two_policies")
    mock.hospital_set(run4, mock.admit_and_discharge())
    mock.pdf("/payer/documents/DOC-POL-CORP-GROUP-HEALTH-2026-88.pdf", os.path.join(run4, "04_policy_schedule_group_arogya.pdf"))
    consent_letter(os.path.join(run4, "05_consent_letter_ramesh_to_aman.pdf"))

    # Run 5: cashless; the TPA pays the hospital, which then issues the updated (settled) bill.
    run5 = folder("run5_cashless")
    mock.start()
    mock.call("POST", "/payer/preauths", headers=HOSPITAL_KEY, json={
        "policy_number": "SURAKSHA-HEALTH-2026-001", "member_name": "Ramesh Sharma", "hospital_id": "HOSP-001",
        "admission_date": "2026-10-02", "diagnosis_text": "Acute Appendicitis (ICD K35.8)", "estimated_amount": 5500000})
    discharge = mock.admit_and_discharge()
    mock.hospital_set(run5, discharge)
    claim = mock.submit("demo-run5-claim", claim_type="cashless")
    mock.clock(6)
    decision = mock.decide(claim, "partially_approved")
    mock.call("POST", f"/payer/claims/{claim}/pay", json={"payee": "hospital", "utr_override": UTR["run5"]})
    tpa, total = decision["approved_amount"], sum(l["amount"] for l in BILL_LINES)
    admission_id = discharge["discharge_summary_doc_id"].replace("DOC-DS-", "")
    letter(os.path.join(run5, "04_final_bill_updated_after_tpa_payment.pdf"),
           "HOSPITAL FINAL BILL - UPDATED AFTER CASHLESS SETTLEMENT (MOCK)", [
               f"Hospital: {HOSPITAL['name']}",
               f"Bill No: BILL-{admission_id[-6:]} (version 2, updated after TPA settlement)",
               "Patient Name: Ramesh Sharma",
               "Admission / Discharge: 2026-10-02 to 2026-10-05",
               "Payer: Suraksha General Insurance (MOCK) through Medivista TPA (MOCK), cashless",
           ], table=[(l["head"], l["amount"]) for l in BILL_LINES], total_label="TOTAL BILL AMOUNT", notes=[
               f"Settlement: Medivista TPA (MOCK) paid Rs {tpa // 100:,} to the hospital on "
               f"2026-10-07 (UTR {UTR['run5']}), claim {claim}.",
               f"Paid by the patient at discharge (non-payable items, co-pay and deductible): Rs {(total - tpa) // 100:,}.",
               "Balance due from the patient: Rs 0. This bill replaces the bill issued at discharge.",
           ])

    # Run 6: no connector. Portal submission, query with hidden instructions, decision, short credit.
    run6 = folder("run6_manual_route")
    mock.start()
    mock.hospital_set(run6, mock.admit_and_discharge())
    portal = mock.call("POST", "/payer/claims", headers={**CLAIMWISE_KEY, "Idempotency-Key": "idem-demo-001"}, json={
        "client_reference": "CLIENT-REF-001", "policy_number": "SURAKSHA-HEALTH-2026-001", "member_name": "Ramesh Sharma",
        "acting_user": "Ramesh Sharma", "claim_type": "reimbursement", "admission_date": "2026-10-02",
        "discharge_date": "2026-10-05", "claimed_amount": 6000000,
        "line_items": [{"head": "Room Rent", "amount": 1500000}, {"head": "Surgeon Fees", "amount": 3500000},
                       {"head": "Medicines", "amount": 1000000}],
        "documents": [{"doc_type": "discharge_summary", "filename": "02_valid_discharge_summary.pdf"}]})["id"]
    query = mock.call("POST", f"/payer/claims/{portal}/query", json={"items": [{
        "code": "DOC_HISTO", "label": "Histopathology Biopsy Report",
        "description": "Please provide signed histopathology report for appendectomy."}],
        "due_days": 15, "inject_malicious": True})
    mock.pdf(f"/payer/documents/{query['letter_doc_id']}.pdf", os.path.join(run6, "04_query_letter_hidden_instructions.pdf"))
    mock.call("POST", f"/payer/claims/{portal}/documents", json={"documents": [
        {"doc_type": "investigation_report", "filename": "biopsy_report.pdf"}]})
    mock.clock(6)
    decision = mock.decide(portal, "partially_approved")  # console lines have no consumables: Rs 53,000
    mock.pdf(f"/payer/documents/{decision['letter_doc_id']}.pdf", os.path.join(run6, "05_decision_letter.pdf"))
    mock.call("POST", f"/payer/claims/{portal}/pay", json={
        "payee": "member", "credit_amount_override": 4900000, "utr_override": UTR["run6"]})  # Rs 4,000 short
    mock.pdf("/bank/accounts/ACC-001/statement.pdf", os.path.join(run6, "06_bank_statement_short_credit.pdf"))

    # Run 7: a fresh claim's documents (the flawed files are in invalid/).
    run7 = folder("run7_failures")
    mock.start()
    mock.hospital_set(run7, mock.admit_and_discharge())


def build_invalid() -> None:
    """Flawed, hostile or unrelated files, drawn with the mock's own generators where it has one."""
    settings.docs_storage_path = INVALID_DIR
    os.makedirs(INVALID_DIR, exist_ok=True)
    path = lambda name: os.path.join(INVALID_DIR, name)  # noqa: E731
    admission = {"id": "ADM-7F3A21C9", "patient_name": "Ramesh Sharma", "admission_date": "2026-10-02",
                 "discharge_date": "2026-10-05", "diagnosis_text": "Acute Appendicitis (Laparoscopic Appendectomy)"}
    claim = {"id": "CLM-4B8E0D12", "claimed_amount": 6000000}

    # Each mock generator writes <doc_id>.pdf into settings.docs_storage_path (here: invalid/).
    generate_discharge_summary_pdf("01_discharge_summary_wrong_patient", {**admission, "patient_name": "Sita Devi"}, HOSPITAL)
    letter(path("02_not_a_claim_document_recipe.pdf"), "MASALA CHAI RECIPE", ["Serves: 2", "Time: 10 minutes"], notes=[
        "Boil two cups of water with crushed ginger and two green cardamom pods.",
        "Add two teaspoons of tea leaves, one cup of milk and sugar to taste. Simmer for three minutes.",
        "Strain into cups and serve hot."])
    generate_final_bill_pdf("03_final_bill_dates_do_not_match", {**admission, "admission_date": "2026-10-15",
                            "discharge_date": "2026-10-18"}, HOSPITAL, BILL_LINES)
    generate_discharge_summary_pdf("04_discharge_summary_outside_policy_period", {**admission,
                                   "admission_date": "2025-08-10", "discharge_date": "2025-08-14"}, HOSPITAL)
    letter(path("05_final_bill_total_does_not_add_up.pdf"), "HOSPITAL FINAL ITEMIZED BILL (MOCK)", [
        f"Hospital: {HOSPITAL['name']}", "Bill No: BILL-A21C9", "Patient Name: Ramesh Sharma",
        "Admission / Discharge: 2026-10-02 to 2026-10-05"],
        table=[(l["head"], l["amount"]) for l in BILL_LINES], total_label="TOTAL CLAIMED AMOUNT", printed_total=8000000)
    generate_final_bill_pdf("06_final_bill_above_sum_insured", admission, HOSPITAL, [
        {"head": "Room Rent - Deluxe Suite (3 days)", "amount": 45000000},
        {"head": "Robotic Surgery Package", "amount": 450000000},
        {"head": "Surgical Implants", "amount": 355000000}])
    generate_query_letter_pdf("07_query_letter_hidden_instructions", claim, {
        "raised_at": "2026-10-08T11:00:00+05:30", "due_at": "2026-10-23T11:00:00+05:30", "items": [{
            "code": "DOC_HISTO", "label": "Histopathology Biopsy Report",
            "description": "Please provide signed histopathology report for appendectomy."}]}, injected_malicious=True)
    generate_decision_letter_pdf("08_decision_letter_without_clause", claim, {
        "outcome": "partially_approved", "decided_at": "2026-10-12T14:00:00+05:30", "approved_amount": 5500000,
        "line_decisions": [
            {"head": "Room & Nursing Charges", "claimed": 1500000, "approved": 1500000, "policy_clause": ""},
            {"head": "Operation Theatre & Surgeon Charges", "claimed": 3500000, "approved": 3000000, "policy_clause": ""},
            {"head": "Pharmacy & Consumables", "claimed": 1000000, "approved": 1000000, "policy_clause": ""}]})
    generate_query_letter_pdf("09_query_letter_asks_again_for_discharge_summary", claim, {
        "raised_at": "2026-10-08T11:00:00+05:30", "due_at": "2026-10-23T11:00:00+05:30", "items": [{
            "code": "DOC_DISCHARGE_CARD", "label": "Discharge card",
            "description": "Discharge card signed by the treating doctor."}]})
    consent_letter(path("10_consent_letter_names_someone_else.pdf"), representative="Rahul Verma")
    consent_letter(path("11_consent_letter_signed_by_wrong_person.pdf"), grantor="Sunita Sharma")
    consent_letter(path("12_consent_letter_expired.pdf"), valid_until="2026-09-30")
    with open(path("13_unsupported_format.txt"), "w", encoding="utf-8") as f:
        f.write("Plain text notes about the hospital stay. Claimwise accepts PDF and image files only.\n")


def generate_all_test_documents() -> None:
    """Replace both fixture folders with a freshly generated set."""
    random_ids = random.Random(2026)
    real_uuid4 = uuid.uuid4
    uuid.uuid4 = lambda: uuid.UUID(int=random_ids.getrandbits(128), version=4)  # stable IDs across runs
    saved = (settings.mock_db_path, settings.docs_storage_path)
    work = tempfile.mkdtemp(prefix="claimwise-fixtures-")
    try:
        for target in (VALID_DIR, INVALID_DIR):
            shutil.rmtree(target, ignore_errors=True)
        build_valid(Mock(work))
        build_invalid()
    finally:
        uuid.uuid4 = real_uuid4
        settings.mock_db_path, settings.docs_storage_path = saved
        shutil.rmtree(work, ignore_errors=True)
    print(f"Valid fixtures: {VALID_DIR}\nInvalid fixtures: {INVALID_DIR}")


if __name__ == "__main__":
    generate_all_test_documents()
