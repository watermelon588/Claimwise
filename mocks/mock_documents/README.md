# Demo document fixtures

Synthetic PDFs for the [demo walkthrough](../../docs/07-delivery/demo-walkthrough.md). Every name, number and record is invented. Each page is marked "MOCK DOCUMENT - NOT A REAL RECORD".

## How they are made

`mocks/mocks/services/generate_test_suite_docs.py` runs the mock services in-process, on a temporary database, through the same Mock Console steps each walkthrough run performs. It keeps every PDF the run uploads. The files therefore match what the Mock Console would download at that point, with the same layout, amounts and dates.

- **Fixed transfer references.** Every settlement uses a fixed UTR (`utr_override`). When the walkthrough sends the same UTR from the Mock Console, a static bank statement matches the live payment.
- **Synthetic IDs differ from live ones.** Claim and admission numbers (`CLM-...`, `ADM-...`) are random in a live session, so a static letter shows a different claim number from the live claim. Claimwise does not check the claim number on uploaded letters, so this does not change the result.
- **Mock-style documents.** Documents the mock cannot produce use the mock's own PDF style: consent letters, and the cashless bill updated after the TPA pays the hospital.
- **Safe to run anytime.** Generation turns webhooks off and never touches `mocks/mock.db` or a running backend.

Regenerate (this replaces both folders):

```bash
cd mocks
uv run python -m mocks.services.generate_test_suite_docs
uv run pytest tests/test_mock_documents.py -q
```

## valid/: one folder per walkthrough run

Common facts:

- Patient: Ramesh Sharma, policy `SURAKSHA-HEALTH-2026-001` (Rs 5,00,000, 2026-01-01 to 2026-12-31, 10% co-pay, Rs 1,000 deductible).
- Stay: Sunrise Hospital (MOCK), admitted 2026-10-02, discharged 2026-10-05.
- Bill: Rs 60,000, made up of room Rs 15,000, OT and surgeon Rs 35,000, pharmacy and consumables Rs 10,000.
- Partial decision: Rs 44,000. Consumables are excluded, then the co-pay and deductible apply.

| Folder | Files | What the run needs them for |
|---|---|---|
| `run1_standard_reimbursement/` | `01_policy_schedule`, `02_discharge_summary`, `03_final_bill`, `04_bank_statement` | Statement credit Rs 44,000 on 2026-10-07, UTR `UTR-DEMO-RUN1` |
| `run2_dispute_fallback/` | `01_revised_decision_letter` | The revised decision after the Ombudsman award: all lines approved, Rs 60,000. Upload it if the connector step 2.4 is skipped |
| `run3_caregiver/` | `01` to `03` as above; `04_consent_letter_ramesh_to_aman` (valid until 2027-06-30); `05_discharge_summary_reissued_v2`; `06_bank_statement_before_credit` (no credit); `07_bank_statement_after_credit` (Rs 44,000, UTR `UTR-DEMO-RUN3`) | Authority proof, version 2 of a document, late credit |
| `run4_two_policies/` | `01_policy_schedule` (Aman `revoked`), `02`, `03`, `04_policy_schedule_group_arogya` (`CORP-GROUP-HEALTH-2026-88`, Rs 3,00,000), `05_consent_letter_ramesh_to_aman` | Revoked representative and a second policy |
| `run5_cashless/` | `01` to `03` (bill as issued at discharge), `04_final_bill_updated_after_tpa_payment` | Updated bill: TPA paid Rs 44,000 to the hospital on 2026-10-07 (UTR `UTR-DEMO-RUN5-HOSPITAL`), patient paid Rs 16,000, balance Rs 0 |
| `run6_manual_route/` | `01` to `03`; `04_query_letter_hidden_instructions`; `05_decision_letter` (Rs 53,000); `06_bank_statement_short_credit` (Rs 49,000, UTR `UTR-DEMO-RUN6`) | The claim made with the Mock Console's default **Submit claim** body, which has no consumables line, so the partial decision is Rs 53,000 and the credit is Rs 4,000 short |
| `run7_failures/` | `01` to `03` | A fresh claim for the failure steps |

## invalid/: files that must be caught or refused

| File | What is wrong | What Claimwise does |
|---|---|---|
| `01_discharge_summary_wrong_patient.pdf` | Patient is Sita Devi | Blocker `name_mismatch` |
| `02_not_a_claim_document_recipe.pdf` | A tea recipe | Rejected as not a claim document; stored copy deleted |
| `03_final_bill_dates_do_not_match.pdf` | Bill dates 2026-10-15 to 2026-10-18 | Blocker `date_mismatch` |
| `04_discharge_summary_outside_policy_period.pdf` | Stay in August 2025 | Warning `outside_policy_period` |
| `05_final_bill_total_does_not_add_up.pdf` | Lines Rs 60,000, printed total Rs 80,000 | Warning `bill_total_mismatch` |
| `06_final_bill_above_sum_insured.pdf` | Bill Rs 85,00,000 | Warning `over_sum_insured` |
| `07_query_letter_hidden_instructions.pdf` | Text telling an AI to approve the claim | Read as data; nothing approved or sent |
| `08_decision_letter_without_clause.pdf` | Rs 5,000 surgeon cut with no clause | Warning `clause_not_cited` |
| `09_query_letter_asks_again_for_discharge_summary.pdf` | Asks for a "Discharge card" | `repeated_request`: names the summary already sent |
| `10_consent_letter_names_someone_else.pdf` | Representative Rahul Verma | Authority refused: the proof names Rahul Verma |
| `11_consent_letter_signed_by_wrong_person.pdf` | Grantor Sunita Sharma, not the patient | Authority refused: the proof is given by Sunita Sharma |
| `12_consent_letter_expired.pdf` | Valid until 2026-09-30 | Authority refused: expired |
| `13_unsupported_format.txt` | Plain text file | Upload refused before reading (PDF, PNG or JPEG only) |

The "What Claimwise does" column describes the checks in `backend/app/agent/`. Unit tests and the live harness cover these checks with their own inputs. These regenerated PDFs have not yet been uploaded to a live Claimwise session.
