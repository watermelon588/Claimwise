# Claimwise Mock Site and Test Documents Guide

Welcome to the Claimwise Mock Systems documentation. This guide explains in plain English what the mock site does, how it is organized, how to use it, and how to test the Claimwise agent using the generated realistic mock documents.

---

## 1. Why Does This Mock Site Exist?

In India, health insurance claims involve several separate organizations:
- **Insurers and Third-Party Administrators (TPAs)** (such as Suraksha General Insurance and Medivista TPA): They hold policy records, review claims, issue deficiency letters (queries), approve or reject payouts, and disburse money.
- **Hospitals** (such as Sunrise Hospital): They admit patients, issue discharge summaries, itemized bills, and handle cashless pre-authorisation requests.
- **Banks** (such as Bharat Demo Bank): They receive the settlement credit through NEFT and produce account statements.
- **Grievance Redressal Officers (GRO) and the Insurance Ombudsman**: They handle disputes when an insurer unfairly rejects or cuts a claim payout.

None of these organizations provide open, public APIs for patient-side apps. To demonstrate and thoroughly test Claimwise without risking real patient records or real money, we created this standalone **Mock Site** (running on port `8100`). It acts as a realistic digital stand-in for all these external parties.

---

## 2. Is the Mock Site End-to-End Ready?

**Yes, the mock site is 100% end-to-end ready for testing the current agent.**

- **Server is fully functional**: Runs on port `8100` with all routes active: Payer (M1), Hospital (M2), Bank (M3), Grievance/Ombudsman (M4), Virtual Clock & Admin (M5), and Event Logging.
- **Data persistence is in place**: Uses a local SQLite database (`mocks/mock.db`) with baseline seed policies, hospitals, and bank accounts.
- **All 14 unit and integration tests pass**: Decision arithmetic, idempotency replays, lost response recovery, document versioning, 14-day grievance turnaround time (TAT), and Ombudsman eligibility rules are verified.
- **Demo PDFs are generated**: Saved in `mocks/mock_documents/`, one folder per walkthrough run plus a flawed set, ready to upload into Claimwise.

---

## 3. Quick Start: How to Run the Mock Site

Open a terminal and run the following commands:

```bash
cd mocks
uv sync
uv run uvicorn mocks.main:app --port 8100 --reload
```

Once running:
- **Status Dashboard**: Visit `http://localhost:8100/` in your browser.
- **Interactive Swagger / API Documentation**: Visit `http://localhost:8100/docs` to view and try every available route interactively.

---

## 4. File System and Directory Structure

The mock site is completely isolated in the `mocks/` folder so it never interferes with the main Claimwise backend or frontend:

```
mocks/
├── pyproject.toml                         # Dependency list (FastAPI, Uvicorn, Pydantic, FPDF2, Pytest)
├── uv.lock                                # Locked dependency tree
├── .env.example                           # Configuration defaults (Port 8100, API keys, Webhook secret)
├── README.md                              # Technical quick start
├── mock.db                                # Local SQLite database (created on startup, gitignored)
│
├── mocks/                                 # Backend Python application
│   ├── main.py                            # FastAPI entry point & status dashboard
│   ├── config.py                          # Application settings
│   ├── db.py                              # Database schema and table setup
│   ├── clock.py                           # Virtual clock (GET/POST /admin/clock)
│   ├── faults.py                          # Fault injection (latency, dropped connections)
│   ├── events.py                          # Event log and HMAC-signed webhook sender
│   ├── auth.py                            # API key checking and idempotency protection
│   ├── routers/                           # Backend routes
│   │   ├── admin.py                       # /admin/reset, /admin/scenarios
│   │   ├── payer.py                       # /payer (policies, preauths, claims, queries, decisions, pay)
│   │   ├── hospital.py                    # /hospital (admissions, discharge, document reissue)
│   │   ├── bank.py                        # /bank (credits, statements)
│   │   └── grievance.py                   # /grievance (grievances, ombudsman complaints, awards)
│   └── services/                          # Business logic
│       ├── payer_logic.py                 # Deduction calculations & IRDAI clause validation
│       ├── pdf_generator.py               # PDF generation utility
│       ├── scenarios.py                   # 9 pre-configured test scenarios & seed data
│       └── generate_test_suite_docs.py    # Generator for the demo fixture PDFs
│
├── mock_documents/                        # The generated test documents
│   ├── README.md                          # Document guide
│   ├── valid/                             # One folder of PDFs per walkthrough run
│   └── invalid/                           # 13 flawed, hostile or unrelated files
│
└── tests/                                 # Automated test suite (14 tests)
    ├── test_clock_faults.py
    ├── test_payer_arithmetic.py
    ├── test_claims_lifecycle.py
    ├── test_hospital_bank.py
    ├── test_grievance_ombudsman.py
    └── test_mock_documents.py
```

---

## 5. Demo Document Fixtures

`mocks/mock_documents/` holds synthetic PDFs for the demo walkthrough, generated by driving the mock services through each walkthrough run, so they match what the Mock Console downloads. `valid/` has one folder per run (standard reimbursement, dispute fallback, caregiver, two policies, cashless, manual route, failures). `invalid/` has 13 flawed, hostile or unrelated files. See the [fixture guide](../../mocks/mock_documents/README.md) for every file, its facts and the check it exercises.

---

## 6. Step-by-Step: How to Test the Agent

### Step 1: Start Both Servers
In terminal 1 (Claimwise Backend):
```bash
cd backend
uv run uvicorn app.main:app --port 8000 --reload
```

In terminal 2 (Mock Site):
```bash
cd mocks
uv run uvicorn mocks.main:app --port 8100 --reload
```

### Step 2: Upload Documents to the Agent
You can upload test documents using the React frontend at `http://localhost:5173/`, or directly via curl / Python to the backend endpoint:

```bash
# Upload valid policy schedule
curl -X POST http://localhost:8000/api/documents \
  -F "file=@mocks/mock_documents/valid/run1_standard_reimbursement/01_policy_schedule.pdf"
```

### Step 3: Observe Agent Behavior
1. **Onboarding**: The agent reads the policy, extracts the members and sum insured, and pauses with a confirmation prompt.
2. **Claim Checklist**: Upload `02_discharge_summary.pdf` and `03_final_bill.pdf` from the same folder. The agent confirms both required documents are present and generates the submission pack.
3. **Flaw Testing**: In a separate thread, upload `invalid/01_discharge_summary_wrong_patient.pdf`. Notice that the agent immediately blocks submission due to the patient name mismatch.
4. **Adversarial Test**: Upload `invalid/07_query_letter_hidden_instructions.pdf`. Verify that the agent safely summarizes the document as data without following the injected override command.

### Step 4: Advance the Virtual Clock
When testing deadlines (such as the 15-day query deadline or 14-day grievance turnaround time), you can advance the mock clock without waiting:

```bash
# Jump forward 16 days
curl -X POST http://localhost:8100/admin/clock/advance \
  -H "Content-Type: application/json" \
  -d '{"days": 16, "hours": 0, "minutes": 0}'
```

---

## 7. Useful Administration Endpoints

| Endpoint | Method | What it does |
|---|---|---|
| `GET /` | GET | Status dashboard with active router list. |
| `GET /docs` | GET | Interactive Swagger UI for testing routes. |
| `POST /admin/reset` | POST | Clears the database and restores baseline seed records. |
| `GET /admin/scenarios` | GET | Lists all 9 pre-built test scenarios. |
| `POST /admin/scenarios/{name}` | POST | Loads a specific scenario (e.g. `repeated_renamed_request` or `rejection_to_ombudsman`). |
| `GET /admin/clock` | GET | Displays the current virtual clock timestamp. |
| `POST /admin/clock/advance` | POST | Moves the clock forward by days, hours, or minutes. |
| `GET /events` | GET | Chronological log of all emitted webhooks and events. |
