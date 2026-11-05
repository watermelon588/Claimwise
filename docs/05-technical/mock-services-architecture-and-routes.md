# Mock External Systems: Architecture and Routes Documentation

Status: Complete (2026-11-05). Implements task MOCK-001 based on `docs/05-technical/external-systems-and-mocks.md`.
Base URL: `http://localhost:8100`
Brand Accent Color: `rgb(248, 179, 0)`

---

## 1. System Overview

Claimwise acts exclusively for the patient or authorized caregiver. Real payers, hospitals, and banks in India do not expose open patient-side APIs. To enable deterministic lifecycle testing, the `mocks/` workspace provides standalone mock services on port 8100:

1. **M1 Payer Service (`/payer`)**: Simulates insurer and TPA adjudication, coverage eligibility, cashless pre-authorisation, reimbursement claims, deficiency query loops, deterministic line-by-line deduction arithmetic, and payment notices.
2. **M2 Hospital Service (`/hospital`)**: Simulates hospital billing, in-patient admissions, cashless pre-auth requests to M1, discharge documentation, and versioned document reissuance.
3. **M3 Bank Service (`/bank`)**: Simulates the patient's bank account, inbound NEFT/RTGS settlement credits, account statements, and mismatch simulation knobs.
4. **M4 Grievance & Ombudsman Service (`/grievance`)**: Simulates Insurer Grievance Redressal Officers (GRO), IRDAI Bima Bharosa complaint intake with 14-day statutory turnaround time (TAT), and Insurance Ombudsman arbitration (financial limit up to Rs 50 Lakh, 30-day compliance tracking, and claim reopening).
5. **M5 Administrative Engine & Controls (`/admin`, `/events`)**: Provides a virtual clock (`/admin/clock`), fault injection (`/admin/faults`), HMAC-signed webhook event streaming (`/events`), database reset (`/admin/reset`), and 9 scenario presets (`/admin/scenarios/{name}`).
6. **M6 Synthetic Document Generator (`mocks.services.pdf_generator`)**: Generates realistic PDF documents for policy schedules, hospital summaries, bills, deficiency letters, settlement advice, and bank statements, all carrying clear header and footer mock disclosures.

---

## 2. Cross-Cutting Design Rules

### 2.1 Currency and Amounts
All monetary values are stored and calculated as integers in **paise** (Rs 1 = 100 paise) to prevent floating-point rounding errors. UI and PDFs format them in rupees.

### 2.2 Security and Boundaries
- Requests to partner endpoints (`/payer/claims`, `/hospital/admissions`, `/bank/accounts/.../credits`, `/grievance/grievances`) must supply header:
  `X-Api-Key: <key>`
  Permitted seed keys: `claimwise-demo-key`, `hospital-demo-key`. Missing or invalid keys return HTTP 401 `UNAUTHORISED`.
- Every JSON response contains `"mock": true`.
- Every generated PDF includes a prominent disclaimer: `"DEMO ARTIFACT - MOCK DOCUMENT - NOT A REAL RECORD"`.

### 2.3 Idempotency
- `POST /payer/claims` requires header `Idempotency-Key: <uuid>`.
- Replaying with the same key and same body returns the cached response with original ID and status.
- Sending the same key with a different request payload returns HTTP 409 `IDEMPOTENCY_CONFLICT`.

### 2.4 Time Control (Virtual Clock)
All timestamps use ISO 8601 with `+05:30` timezone offset (Asia/Kolkata). The service reads from a database-backed virtual clock, never raw system time, allowing tests to leap forward 15 or 30 days deterministically.

### 2.5 Webhooks and Signatures
State mutations emit structured events to `CLAIMWISE_WEBHOOK_URL`:
- Header: `X-Mock-Signature: sha256=<hmac_sha256(body, MOCK_WEBHOOK_SECRET)>`
- Body schema:
  ```json
  {
    "event_id": "EVT-...",
    "event_type": "claim.decided",
    "occurred_at": "2026-10-12T14:00:00+05:30",
    "resource": {
      "type": "claim",
      "id": "CLM-0001",
      "version": 4
    },
    "data": { ... },
    "mock": true
  }
  ```
- Polling fallback: `GET /events?after=<event_id>` returns unread events in sequential order.

---

## 3. Database Schema

All mock persistence is managed in `mocks/mock.db` via SQLite3:

| Table | Primary Key | Key Columns |
|---|---|---|
| `clock` | `id=1` | `virtual_time` (ISO 8601 with +05:30) |
| `faults` | `id=1` | `drop_response_after_commit`, `delay_ms`, `error_rate`, `duplicate_webhooks`, `webhook_down` |
| `idempotency` | `(key, endpoint)` | `request_hash`, `status_code`, `response_body`, `created_at` |
| `events` | `id` | `event_type`, `occurred_at`, `resource_type`, `resource_id`, `resource_version`, `payload`, `status` |
| `policies` | `id` | `policy_number`, `insurer_name`, `tpa_name`, `sum_insured`, `balance_sum_insured`, `room_rent_limit_per_day`, `copay_percent`, `deductible`, `sub_limits`, `members`, `authorised_representatives`, `version` |
| `preauths` | `id` | `policy_id`, `member_id`, `hospital_id`, `estimated_amount`, `approved_amount`, `status`, `version` |
| `claims` | `id` | `client_reference`, `policy_id`, `member_id`, `claim_type`, `claimed_amount`, `line_items`, `documents`, `status`, `version` |
| `queries` | `id` | `claim_id`, `raised_at`, `due_at`, `items`, `status`, `answered_at` |
| `decisions` | `id` | `claim_id`, `outcome`, `decided_at`, `approved_amount`, `line_decisions`, `rejection_reason`, `policy_clause`, `letter_doc_id` |
| `payments` | `id` | `claim_id`, `amount`, `utr`, `paid_at`, `payee`, `bank_account_last4` |
| `hospitals` | `id` | `name`, `city`, `network_insurers` |
| `admissions` | `id` | `hospital_id`, `patient_name`, `policy_number`, `admission_date`, `discharge_date`, `diagnosis_text`, `status`, `deposit_amount`, `deposit_status` |
| `hospital_documents`| `id` | `admission_id`, `doc_type`, `version`, `issued_at`, `file_path` |
| `bank_accounts` | `id` | `holder_name`, `account_last4`, `ifsc` |
| `bank_credits` | `id` | `account_id`, `amount`, `utr`, `credited_at`, `narration` |
| `grievances` | `id` | `level`, `claim_id`, `filed_at`, `acknowledged_at`, `due_at`, `status`, `resolution_text` |
| `ombudsman_complaints` | `id` | `grievance_id`, `claim_id`, `filed_at`, `eligible`, `eligibility_reason`, `status`, `award_amount`, `compliance_due_at` |

---

## 4. Complete Route Reference

### 4.1 Admin, Clock & Faults

#### `POST /admin/reset`
- **Purpose**: Drops all tables, re-runs migrations, and populates seed records.
- **Request**: Empty body.
- **Response**: `200 OK` `{ "status": "success", "message": "...", "mock": true }`

#### `GET /admin/clock`
- **Purpose**: Retrieve current virtual clock timestamp.
- **Response**: `200 OK` `{ "current_time": "2026-10-01T10:00:00+05:30", "mock": true }`

#### `POST /admin/clock/advance`
- **Purpose**: Advance the virtual clock by relative days, hours, and minutes.
- **Body**: `{ "days": 5, "hours": 2, "minutes": 0 }`
- **Response**: `200 OK` `{ "current_time": "2026-10-06T12:00:00+05:30", "mock": true }`

#### `POST /admin/clock/set`
- **Purpose**: Explicitly jump the virtual clock to a specific timestamp.
- **Body**: `{ "at": "2026-11-15T14:30:00+05:30" }`
- **Response**: `200 OK` `{ "current_time": "2026-11-15T14:30:00+05:30", "mock": true }`

#### `GET /admin/faults` / `POST /admin/faults`
- **Purpose**: Read or set active fault injection rules.
- **Body**:
  ```json
  {
    "drop_response_after_commit": false,
    "delay_ms": 0,
    "error_rate": 0.0,
    "duplicate_webhooks": false,
    "webhook_down": false
  }
  ```

#### `GET /admin/scenarios`
- **Purpose**: Lists all 9 pre-configured test scenarios.

#### `POST /admin/scenarios/{name}`
- **Purpose**: Clears database and loads the named scenario fixture.
- **Supported names**:
  - `standard_reimbursement`
  - `cashless_partial`
  - `repeated_renamed_request`
  - `partial_with_mismatched_credit`
  - `rejection_to_ombudsman`
  - `silent_insurer`
  - `caregiver_consent_change_two_policies`
  - `lost_submit_response`
  - `malicious_document_text`

---

### 4.2 M1 Payer Service (`/payer`)

#### `GET /payer/policies/{policy_number}`
- **Purpose**: Fetch policy terms, coverage dates, limits, and covered members.
- **Returns**: HTTP 200 with policy record, or 404 `POLICY_NOT_FOUND`.

#### `POST /payer/eligibility`
- **Purpose**: Evaluate if a member is covered for an admission date.
- **Body**: `{ "policy_number": "...", "member_name": "...", "treatment_date": "2026-10-10" }`
- **Returns**: `{ "eligible": true, "reasons": [], "balance_sum_insured": 50000000, "mock": true }`

#### `POST /payer/preauths`
- **Header**: `X-Api-Key: hospital-demo-key`
- **Body**: `{ "policy_number": "...", "member_name": "...", "hospital_id": "...", "admission_date": "...", "diagnosis_text": "...", "estimated_amount": 5000000 }`
- **Returns**: `200 OK` `{ "id": "PA-...", "status": "approved", "approved_amount": 5000000, "mock": true }`

#### `POST /payer/claims`
- **Headers**: `X-Api-Key: claimwise-demo-key`, `Idempotency-Key: <uuid>`
- **Body**:
  ```json
  {
    "client_reference": "CLIENT-REF-001",
    "policy_number": "SURAKSHA-HEALTH-2026-001",
    "member_name": "Ramesh Sharma",
    "acting_user": "Aman Sharma",
    "claim_type": "reimbursement",
    "admission_date": "2026-10-02",
    "discharge_date": "2026-10-05",
    "claimed_amount": 6000000,
    "line_items": [
      { "head": "Room Rent", "amount": 1500000 },
      { "head": "Surgeon Fees", "amount": 3500000 },
      { "head": "Medicines", "amount": 1000000 }
    ],
    "documents": []
  }
  ```
- **Returns**: `201 Created` with claim ID and status `submitted`.
- **Errors**: 401 `UNAUTHORISED`, 403 `NOT_AUTHORISED_REPRESENTATIVE`, 409 `IDEMPOTENCY_CONFLICT`, 422 `MEMBER_NOT_COVERED`.

#### `GET /payer/claims`
- **Query Param**: `client_reference` (optional)
- **Purpose**: Recovers a submitted claim when an HTTP connection was dropped after commit.

#### `GET /payer/claims/{claim_id}`
- **Purpose**: Fetches the complete claim bundle (claim details, queries, decisions, and payment notices).

#### `POST /payer/claims/{claim_id}/query` (Operator)
- **Body**: `{ "items": [{ "code": "DOC_BILL", "label": "Pharmacy Bill", "description": "Original bill required" }], "due_days": 15, "inject_malicious": false }`
- **Effect**: Changes status to `query_raised`, increments `version`, generates a query letter PDF, and fires `claim.query_raised`.

#### `POST /payer/claims/{claim_id}/documents`
- **Body**: `{ "documents": [{ "doc_type": "pharmacy_bill", "filename": "receipt.pdf" }] }`
- **Effect**: Resolves open queries, moves status to `under_review`, and fires `claim.query_answered`.

#### `POST /payer/claims/{claim_id}/decide` (Operator)
- **Body**:
  ```json
  {
    "outcome": "partially_approved",
    "rejection_reason": null,
    "policy_clause": null,
    "line_decisions": [
      { "head": "Room Rent", "claimed": 1500000, "approved": 1000000, "policy_clause": "Clause 3.2 (Room Rent Cap)" }
    ]
  }
  ```
- **Effect**: If `line_decisions` is omitted, executes deterministic calculations (`calculate_line_decisions`). Generates decision letter PDF and transitions status to `approved`, `partially_approved`, or `rejected`.
- **Enforcement**: Raises 422 `CLAUSE_REQUIRED` if any deduction or rejection lacks a policy clause.

#### `POST /payer/claims/{claim_id}/pay` (Operator)
- **Body**: `{ "payee": "member", "bank_account_last4": "8921", "credit_amount_override": null, "skip_credit": false }`
- **Effect**: Records payment notice, decrements policy `balance_sum_insured`, transitions status to `payment_advised`, posts bank credit to M3, and fires `payment.advised`.

#### `POST /payer/claims/{claim_id}/reopen` (Operator)
- **Purpose**: Reopens a rejected or partially approved claim after an Ombudsman award or grievance resolution. Transitions status to `reopened`.

#### `POST /payer/claims/{claim_id}/withdraw`
- **Purpose**: Member voluntarily withdraws an open claim. Transitions status to `withdrawn`.

---

### 4.3 M2 Hospital Service (`/hospital`)

#### `POST /hospital/admissions`
- **Header**: `X-Api-Key: hospital-demo-key`
- **Body**: `{ "hospital_id": "HOSP-001", "patient_name": "Ramesh Sharma", "policy_number": "...", "admission_date": "2026-10-02", "diagnosis_text": "Appendicitis", "deposit_amount": 500000 }`
- **Returns**: `200 OK` with `admission_id` and status `admitted`.

#### `POST /hospital/admissions/{admission_id}/discharge`
- **Query Param**: `discharge_date=2026-10-05`
- **Effect**: Generates initial Discharge Summary PDF (`DOC-DS-...`) and Final Itemized Bill PDF (`DOC-BILL-...`).

#### `POST /hospital/documents/{doc_id}/reissue`
- **Body**: `{ "corrected_diagnosis": "Appendicitis (Duration 5 days)", "corrected_line_items": null }`
- **Effect**: Increments document `version` to `v2`, updates database records, and generates a new versioned PDF while keeping the prior version intact.

#### `GET /hospital/documents/{doc_id}.pdf`
- **Purpose**: Stream the generated PDF file for manual download and upload into Claimwise.

---

### 4.4 M3 Bank Service (`/bank`)

#### `POST /bank/accounts/{account_id}/credits`
- **Header**: `X-Api-Key: claimwise-demo-key`
- **Body**: `{ "amount": 4230000, "utr": "UTR-12345678", "narration": "SETTLEMENT CREDIT", "credited_at": null }`
- **Returns**: `200 OK` with `credit_id` and confirmation.

#### `GET /bank/accounts/{account_id}/statement`
- **Returns**: JSON list of all credits and total credited amount.

#### `GET /bank/accounts/{account_id}/statement.pdf`
- **Returns**: Generated bank statement PDF formatted with Bharat Demo Bank branding and mock notices.

---

### 4.5 M4 Grievance & Ombudsman Service (`/grievance`)

#### `POST /grievance/grievances`
- **Header**: `X-Api-Key: claimwise-demo-key`
- **Body**: `{ "claim_id": "CLM-0001", "level": "insurer_gro", "complaint_text": "Unjustified deduction" }`
- **Effect**: Automatically creates acknowledgement record and sets `due_at` to exactly `filed_at + 14 days` per IRDAI Master Circular rules.

#### `POST /grievance/grievances/{grievance_id}/resolve` (Operator)
- **Body**: `{ "status": "resolved", "resolution_text": "Internal review findings..." }`
- **Returns**: `200 OK` with updated status.

#### `POST /grievance/ombudsman`
- **Header**: `X-Api-Key: claimwise-demo-key`
- **Body**: `{ "grievance_id": "GRV-0001", "claim_id": "CLM-0001", "complaint_summary": "Disputing repudiation" }`
- **Eligibility Validation**:
  - Rejects with `eligible: false` if claim exceeds the statutory pecuniary ceiling of Rs 50 Lakh.
  - Rejects with `eligible: false` if the insurer has not replied and fewer than 30 days have passed since grievance filing.
  - Returns `eligible: true` with status `registered` once the insurer resolution is rejected or 30 days have lapsed.

#### `POST /grievance/ombudsman/{ombudsman_id}/award` (Operator)
- **Body**: `{ "award_amount": 5000000, "award_notes": "Insurer instructed to pay", "reopen_claim": true }`
- **Effect**: Sets `compliance_due_at` to `award + 30 days`. When `reopen_claim: true`, updates the corresponding claim in M1 to `reopened`.

#### `POST /grievance/ombudsman/{ombudsman_id}/comply` (Operator)
- **Query Param**: `complied=true`
- **Effect**: Marks the Ombudsman award as `complied` or `not_complied`.

---

### 4.6 Events & Webhooks (`/events`)

#### `GET /events`
- **Query Param**: `after=<event_id>` (optional)
- **Purpose**: Sequential event log polling for catch-up and audit.

---

## 5. Function Documentation

### 5.1 Payer Adjudication Engine (`mocks.services.payer_logic`)

#### `calculate_line_decisions(...)`
```python
def calculate_line_decisions(
    line_items: list[dict[str, Any]],
    room_rent_limit_per_day: int,
    days_admitted: int,
    sub_limits: list[dict[str, Any]],
    copay_percent: int,
    deductible: int,
    balance_sum_insured: int,
) -> tuple[int, list[dict[str, Any]], list[str]]:
```
- **Description**: Executes deterministic claim arithmetic following standard Indian insurance practice:
  1. Computes actual daily room rent. If greater than `room_rent_limit_per_day`, derives ratio `allowed / actual` and applies proportionate deductions to room rent, nursing, and medical practitioner charges.
  2. Identifies non-payable consumables (gloves, PPE, administrative fees) and zeroes them out citing Clause 4.1.
  3. Checks ailment sub-limits (e.g. Cataract cap) and truncates exceeding charges.
  4. Deducts member co-payment percentage on total admissible charges.
  5. Applies policy deductible.
  6. Caps net approved sum by `balance_sum_insured`.
- **Returns**: `(net_approved_amount, line_decisions, clauses_cited)`.

#### `validate_decision_clauses(...)`
```python
def validate_decision_clauses(
    outcome: str,
    line_decisions: list[dict[str, Any]],
    rejection_reason: str | None,
    policy_clause: str | None
) -> None:
```
- **Description**: Enforces IRDAI compliance rules:
  - If outcome is `rejected`, requires non-empty `rejection_reason` and `policy_clause`.
  - If outcome is `partially_approved`, ensures that every line item where `approved < claimed` has an associated non-empty `policy_clause`.
- **Raises**: `HTTPException(422, code="CLAUSE_REQUIRED")` on violation.

---

### 5.2 Synthetic Document Generator (`mocks.services.pdf_generator`)

#### `MockDocumentPDF`
- **Description**: Subclass of `fpdf.FPDF` injecting top header disclaimer `"DEMO ARTIFACT - MOCK DOCUMENT - NOT A REAL RECORD"` and bottom footer with page numbering and mock notice.

#### `generate_policy_pdf(doc_id: str, policy: dict) -> str`
- Generates a PDF health insurance policy schedule listing insurer, TPA, floater limits, room rent cap, deductible, and covered members.

#### `generate_discharge_summary_pdf(doc_id: str, admission: dict, hospital: dict, version: int = 1) -> str`
- Generates an in-patient discharge summary detailing diagnosis, clinical course, and post-discharge advice. Supports version tags (e.g. v1, v2).

#### `generate_final_bill_pdf(doc_id: str, admission: dict, hospital: dict, line_items: list) -> str`
- Generates an itemized hospital bill with bordered table of charges and total claimed amount.

#### `generate_query_letter_pdf(doc_id: str, claim: dict, query: dict, injected_malicious: bool = False) -> str`
- Generates a formal deficiency letter listing required documents and submission due date. When `injected_malicious=True`, embeds adversarial prompt text to test Claimwise data isolation.

#### `generate_decision_letter_pdf(doc_id: str, claim: dict, decision: dict) -> str`
- Generates a settlement advice letter displaying approved sums, line item deductions, and cited policy clauses.

#### `generate_bank_statement_pdf(doc_id: str, account: dict, credits: list) -> str`
- Generates an official bank account statement table displaying transaction dates, UTR numbers, and credited sums.

---

### 5.3 Clock and Fault Management (`mocks.clock`, `mocks.faults`)

#### `advance_time(days: int = 0, hours: int = 0, minutes: int = 0, conn = None) -> str`
- Adds the requested time delta to the current virtual clock timestamp in `clock.virtual_time` and commits to SQLite.

#### `set_time(at_iso: str, conn = None) -> str`
- Explicitly overrides the clock with a target ISO 8601 string.

#### `apply_ingress_faults(conn = None) -> None`
- Evaluates active flags in `faults` table. Introduces artificial latency via `asyncio.sleep` or injects random 500 errors based on `error_rate`.

---

### 5.4 Authentication & Idempotency (`mocks.auth`)

#### `verify_api_key(api_key: str) -> str`
- Verifies that `X-Api-Key` matches one of `MOCK_API_KEYS`. Raises 401 `UNAUTHORISED` if invalid.

#### `check_idempotency(conn, key: str, endpoint: str, request_body_bytes: bytes)`
- Computes SHA-256 hash of the request body. If the key exists with the same hash, returns the cached response. If the hash differs, raises 409 `IDEMPOTENCY_CONFLICT`.

#### `record_idempotency(conn, key, endpoint, request_body_bytes, status_code, response_body, created_at)`
- Persists request hash and serialized response in `idempotency` table.

---

## 6. Verification and Test Results

A dedicated Pytest test suite in `mocks/tests/` verifies the implementation:

```
tests/test_claims_lifecycle.py::test_policy_lookup_and_eligibility PASSED
tests/test_claims_lifecycle.py::test_claim_submission_idempotency_and_recovery PASSED
tests/test_claims_lifecycle.py::test_claim_query_decide_and_pay_lifecycle PASSED
tests/test_clock_faults.py::test_clock_advance_and_set PASSED
tests/test_clock_faults.py::test_faults_configuration PASSED
tests/test_grievance_ombudsman.py::test_grievance_filing_and_tat PASSED
tests/test_grievance_ombudsman.py::test_ombudsman_eligibility_rules PASSED
tests/test_hospital_bank.py::test_hospital_admission_discharge_and_reissue PASSED
tests/test_hospital_bank.py::test_bank_credit_and_statement_pdf PASSED
tests/test_payer_arithmetic.py::test_room_rent_proportionate_deduction PASSED
tests/test_payer_arithmetic.py::test_copay_and_deductible PASSED
tests/test_payer_arithmetic.py::test_sub_limit_enforcement PASSED
tests/test_payer_arithmetic.py::test_clause_validation_failure PASSED

13 passed in 38.27s
```
