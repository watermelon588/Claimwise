# Complete journeys

Status: each journey below was run live against the prototype on 2026-11-06 (session 037). It used synthetic documents, the real models, Postgres checkpoints, the connector gateway and the mock payer, hospital and bank. Results per check: [validation-plan.md](../07-delivery/validation-plan.md). Functions: [function catalogue](../05-technical/function-catalogue.md). States: [G2](../04-architecture/g2-lifecycle-state.md). Harness: `e2e/live_e2e.py`.

The brief asks for three complete journeys: a standard case, a materially different user situation, and a failure or disagreement that continues into follow-up, with at least one continuing past the first apparent success. They are A (J1), B (J2) and C (J5, J6, J7). The household journey D (J3) and the refused representative E (J4) are further branches.

## A. Standard reimbursement: the patient claims through a connected account (J1)

Situation: Ramesh Sharma paid the hospital and claims the money back from an individual policy. The TPA account is connected.

| # | User input | Functions | State transition | External action | Evidence of outcome |
|---|---|---|---|---|---|
| 1 | Uploads the policy schedule | API upload, M1, O1 (model reads), O2, O3 pause | Document parsed; policy pending | None | Policy card with number and members (V-01) |
| 2 | Corrects the TPA name, confirms | `/resume`, O3, O2 | Policy confirmed; `corrected_fields: ["tpa"]` | None | Corrected name later printed in the pack (V-02) |
| 3 | "I am the patient myself, Ramesh Sharma." | I1, A1, T1 `record_role`, O2 | Onboarding complete | None | `missing: []` (V-03) |
| 4 | Asks for a poem | I1, R1 | No change | None | Fixed reply naming the current step (V-06) |
| 5 | "This is a reimbursement claim." | A1, T1 `update_claim` | `claim_type: reimbursement` | None | Saved by the model's tool call (V-37) |
| 6 | Uploads a recipe by mistake | O1 | Document rejected, file deleted | None | Not on disk, not in the pack (V-04) |
| 7 | Uploads discharge summary and bill | O1, C1 | Checklist complete, no blocking issue | None | Prepare claim pack offered (V-05) |
| 8 | Prepare claim pack, Approve | X1 `prepare_pack`, pause, `/resume` | `preparing` to `approved_to_submit`; approval hash stored | None | Pack PDF with cover letter, and an EML with attachments (V-07, V-08) |
| 9 | Connects the TPA account, Submit | X1 `submit_via_connector` | `submitted`, claim number stored | Gateway: look up the reference, then submit with the idempotency key | One claim at the payer; Submit no longer offered (V-09, V-29) |
| 10 | Opens the claim 20 days later | M1 reminders | Overdue reminder | None | "Settlement overdue" notice (V-32) |
| 11 | (Insurer decides and pays) | Signed webhook, M1 `read_claim`, C1, P1 | `decided` to `payment_reported`; overdue reminder resolved | Gateway reads the claim | Decision and payment shown without user action (V-11, V-32) |
| 12 | Uploads the bank statement PDF from the mock bank | O1, P1 | `payment_verified` | None | Credit matched by UTR (V-15) |

Completion: the claim is complete only when the bank credit matches. The settlement letter alone leaves it at `payment_reported`.

## B. Caregiver with a disputed decision, continuing past the first apparent success (J2)

Situation: Aman Sharma, a caregiver, acts for the patient, Ramesh Sharma. Aman is not the policyholder, so Claimwise needs recorded authority first. The first decision deducts money; Aman disputes it, takes it to the Ombudsman, and the insurer revises.

| # | User input | Functions | State transition | External action | Evidence of outcome |
|---|---|---|---|---|---|
| 1 | Policy confirmed; "I am helping the patient, Ramesh" | O1 to O3, T1 `record_role`, O2 | Onboarding missing `authority` | None | No claim buttons until authority is recorded (V-03) |
| 2 | Uploads the consent letter and records authority under another name | `/authority` | Refused | None | 422 "The proof names Aman Sharma ..." (V-19) |
| 3 | Records authority as Aman, with scope and expiry | `/authority` | Authority active, audited | None | Claim work unlocked (V-19) |
| 4 | Uploads the bill twice, then a corrected bill | API upload, O1 `version_check`, X1 `replace_version` | 409 for the identical file; version 2 replaces version 1 | None | Old bill superseded (V-18) |
| 5 | Approves the pack and connects, then withdraws consent before submitting | `/authority/withdraw` | Approval cleared; writes blocked | None | Submit refused (V-20) |
| 6 | Re-records authority, approves again, submits | X1, `submit_via_connector` with `acting_user` | `submitted` | Gateway submit | Payer accepts with Aman as the acting user (V-09) |
| 7 | (Partial decision, payment made) | M1, C1, P1 | `payment_reported` | Gateway read | Deductions compared line by line (V-14) |
| 8 | Draft grievance, approve, record the filing date (a future date first) | X1 `draft_grievance`, pause, `grievance_sent` | Dispute `grievance_filed` | User files it (manual handoff) | Future date refused; 14-day reminder raised (V-23) |
| 9 | Uploads the insurer's reply rejecting the grievance | O1, `ombudsman_check` | Ombudsman route open | None | Draft Ombudsman complaint offered (V-24) |
| 10 | Approves the complaint, records the filing | X1 `draft_ombudsman`, `ombudsman_sent` | Dispute `ombudsman_filed` | User files it | Complaint shown for approval first (V-24) |
| 11 | Uploads the revised decision | O1, C1, P1, `dispute_view` | Dispute `revised`; payment `top_up_due` | None | Extra money shown as a top-up due, not a bank error. Documents and submission untouched (V-25) |
| 12 | Uploads the top-up settlement letter and a bank statement showing the top-up credit | O1, C1, P1 | `top_up_due` clears (a payment dated after the revised decision exists); the top-up credit is matched by UTR or amount; `payment_verified` | None | **Specification (not run):** expected from `top_up_due` and `check_payment` in `backend/app/agent/payment.py`. Unit test `test_top_up_due_after_a_revised_decision` covers the top-up and the short-payment check after a revision; the verified credit is not yet run live |

Why this passes the first apparent success: "payment made" at step 7 is not the end. The dispute reopens only the decision and the payment check, and the claim is complete when the top-up arrives in the bank (step 12).

## C. Failure and follow-up: query, lost answer, outage, manual route (J5, J6, J7)

| Journey | What goes wrong | What Claimwise does | Evidence |
|---|---|---|---|
| J5 Insurer query | The TPA asks again for the discharge summary under another name ("Discharge Card") and asks for a lab report | Flags the repeated request with the earlier file and date, and drafts a reply. Offers "Send 2 documents" only after the lab report is uploaded, pauses for approval, then answers through the connector | Query answered at the payer; stage back to submitted (V-12, V-13) |
| J6 Lost answer | The payer saves the claim but its answer is lost (fault `drop_response_after_commit`) | Looks up the client reference and adopts the claim, so nothing is resent | Exactly one claim at the payer (V-10) |
| J6 Outage | Every payer call fails | Submission marked unconfirmed, the turn still completes, and opening the claim works. Once the outage ends, "Check submission" says the payer never got it and points to "Try submitting again", which looks up first and reuses the key | One claim after the retry (V-10, V-36) |
| J7 No connection | The user submits on the insurer's portal | Records the date (future dates refused) and starts the 15-day clock. A mock query letter carries a hidden instruction: it is read as data, nothing is approved. The user answers by post and records the date. The decision letter (a mock PDF) is read with its amounts and clause. The bank credit is short | Stage `payment_mismatch` with the shortfall (V-13, V-14, V-16, V-26, V-33) |

## D. Household with two policies (J3)

Ramesh is covered by an individual policy and an employer's group policy. Both are confirmed, so Claimwise asks which one to claim first (`choose_policy`) and blocks the pack until the claimant chooses. After the first insurer's partial decision, "Start balance claim" archives the first round's letters, encloses the decision, and builds a pack for only the unpaid balance on the second policy. That pack is approved and submitted as a second claim (V-22).

## E. Representative not registered at the payer (J4)

A caregiver with valid proof submits, but the payer refuses because it does not recognise the representative. Claimwise records the refusal with its reason and keeps the connection (a refusal is not an expired login). It does not retry; the caregiver must register with the insurer first (V-21).

---

Previous: [Mock External Systems: Architecture and Routes Documentation](../05-technical/mock-services-architecture-and-routes.md) | [Index](../../README.md) | Next: [UX sketches](ux-sketches.md)
