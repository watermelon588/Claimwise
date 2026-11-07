# Lifecycle map

Status: Draft, 2026-11-08. Grounded in the prototype: states from [G2](../04-architecture/g2-lifecycle-state.md), functions from [G3](../04-architecture/g3-function-execution.md) and the [function catalogue](../05-technical/function-catalogue.md), evidence from the live run in [validation-plan.md](../07-delivery/validation-plan.md) (V-ids). Anything not built is labelled **Proposed** or **Specification (not run)**.

One claim is one thread with one checkpoint. Every checkpoint below reads and writes that same state, so a later stage never starts from scratch. The branches and the paths that rejoin are in the [branch matrix](branch-matrix.md).

## Overview

| # | Checkpoint | Starts when | Ends when (proof) | Main functions | Claim stage (G2 lane B) |
|---|---|---|---|---|---|
| 1 | Before submission | First upload on a new thread | Pack approved by its content hash | O1, O2, O3, C1, X1, T1 | `preparing` to `approved_to_submit` |
| 2 | During submission | User presses Submit, or records a manual filing | Payer claim id read back, or a user-recorded filing date | X1 `submit_via_connector`, M1 | `submitted` |
| 3 | While waiting | Claim is at the payer | A decision letter is on file | M1, C1, X1 (query reply) | `submitted`, `query_raised` |
| 4 | At a decision | A decision is read (connector record or upload) | Outcome classified: full, partial, rejected or unclear | O1, C1 | `decided` |
| 5 | After a decision | Decision on file | Credit matched, or a dispute is resolved and paid | P1, X1 (grievance, Ombudsman, balance claim) | `payment_reported`, `payment_mismatch`, `payment_verified` |
| 6 | After resolution | Payment verified or dispute closed | User keeps, exports or deletes the case | Pack export, delete routes | Unchanged; case kept as evidence |

## 1. Before submission: authority, route, policy context and evidence

| Question | Answer |
|---|---|
| What triggers it? | The user opens a new case and uploads the policy schedule. |
| What does the user want? | A complete, correct claim pack without learning the insurer's checklist. |
| What context is needed? | Confirmed policy facts (insurer, TPA, members, sum insured, period); who is acting (patient or caregiver) and their authority; claim type (cashless or reimbursement); which policy to claim first if there are two; discharge summary and bill. |
| What can run now? | O1 reads each upload into a type and facts. O2 lists what is missing. C1 checks names, dates, policy period, bill arithmetic and sum insured (V-05). Rejected files are deleted at once (V-04). |
| What must wait? | Policy facts wait for the user's confirmation or correction (O3 pause, V-01, V-02). A caregiver waits for recorded authority checked against the proof (V-19). Two policies wait for the claimant's choice (V-22). The pack waits for approval of its exact content (V-07). |
| What can go wrong? | Wrong or unrelated file (rejected); a name or date conflict (issue raised); an exact duplicate (409) or a corrected version (version choice, V-18); a bad correction value (422, V-02); authority missing, expired or naming someone else (V-19); the model cannot read a file (marked failed, upload again). |
| Who acts next? | The user: confirm, correct, choose, upload or approve. Claimwise never fills a gap by guessing. |
| What proves success? | `missing: []`, no blocking issue, and `submission_approval` equal to the current pack hash (G2 lane C "approved"). |
| After success | The Submit button (connected route) or the manual-filing form appears. |
| After failure | The checklist names the exact missing item or conflict; nothing is sent. |
| After silence | The pause stays in the checkpoint indefinitely and survives a restart (V-34). Nothing expires on its own except caregiver authority, which blocks writes after its expiry date. |

## 2. During submission: who does what, and acknowledgement

| Question | Answer |
|---|---|
| What triggers it? | The user presses Submit with a connected TPA account, or records that they filed on the insurer's portal or by post. |
| What does the user want? | The claim filed once, with proof that the insurer has it. |
| What context is needed? | The approved pack and its hash; the client reference derived from thread and pack (also the idempotency key); the connection and the acting user (caregiver authority). |
| What can run now? | Connected route: X1 looks up the reference at the payer first, then submits with the same key (V-09). Manual route: the user records the filing date; future or malformed dates are refused (V-33). |
| What must wait? | Nothing after approval. A withdrawn authority blocks the write (V-20); an expired connection asks the user to reconnect. |
| What can go wrong? | Answer lost after the payer saved the claim (V-10); payer down (V-36); payer refuses the representative (V-21); double click (V-31). |
| Who acts next? | Connected: Claimwise and the payer. Manual: the user files, then records it. The hospital and TPA act on their side outside Claimwise. |
| What proves success? | Connected: the payer's claim id read back or found by reference (**confirmed**). Manual: the user-recorded date (**recorded**, not confirmed by the insurer). |
| After success | Stage `submitted`; the 15-day settlement clock starts from the submission date. |
| After failure | Lost answer or outage: status `unconfirmed`, the turn completes, and the lookup repeats on the next open or "Check submission" (V-10, V-36). Refusal: shown with its reason, not retried (V-21). |
| After silence | M1 repeats the lookup whenever the thread opens; nothing is ever resent blind. |

## 3. While waiting: new requests, deadlines and conflicting messages

| Question | Answer |
|---|---|
| What triggers it? | A signed payer webhook (V-11), opening the thread (M1 `read_claim`), or the user uploading an insurer letter. |
| What does the user want? | To know what the insurer wants, by when, and whether it was already sent. |
| What context is needed? | Every document already on file with its upload time; the query's requested items and due date; the submission and connection. |
| What can run now? | M1 reads the claim and records the query as a letter with source `connector`. C1 matches each requested item to documents held before the query and flags a repeat under a new name (`repeated_request`, V-12). X1 drafts the reply. |
| What must wait? | The reply waits for any missing document and then for the user's approval of exactly what will be sent (V-13). |
| What can go wrong? | The same document asked for again under another name (V-12); instructions hidden in a letter (read as data, V-26); a lost or forged webhook (forged refused, lost recovered on next open, V-11); a missed due date. |
| Who acts next? | The user uploads the missing item and approves; Claimwise answers through the connector, or the user replies by post and records the date. |
| What proves success? | Connected: the payer shows the query answered and the stage returns to `submitted` (V-13). Manual: the user-recorded reply date. |
| After success | Waiting resumes. The rule allows 15 days from the last document the insurer asked for; Claimwise counts from the recorded submission date and says so in the reminder. |
| After failure | The reply stays a draft; the query stays open with its due date. |
| After silence | `settlement_overdue` is raised when 15 days pass with no payment (V-32), and resolved when the decision arrives. |

## 4. At a decision: full, partial, rejected or unclear

| Question | Answer |
|---|---|
| What triggers it? | A decision read from the connector, or an uploaded decision letter. |
| What does the user want? | To know how much was approved, what was cut and why, and what to do next. |
| What context is needed? | The bill lines, the policy facts, the decision letter's amounts, deductions and cited clauses. |
| What can run now? | O1 reads the letter; C1 compares it line by line and flags deductions without a clause (`clause_not_cited`, V-14). Amounts are computed in code, never by the model. |
| What must wait? | Any challenge waits for the user's decision to dispute and their approval of the letter (V-23). |
| What can go wrong? | A letter that cannot be read (`unreadable_document`); amounts that do not add up; instructions in the letter (ignored, V-26). |
| Who acts next? | Full: the bank (pay). Partial: the user decides whether to dispute. Rejected: the user decides on the grievance route. Unclear: the user uploads a readable copy or asks the insurer. |
| What proves success? | Stage `decided` with outcome, approved amount and per-line differences on file. |
| After success | Full or partial goes to payment checking (checkpoint 5); rejected sets payment `none_due` and offers the dispute route. |
| After failure | The document is marked failed or the issue is shown; the stage does not move on guesses. |
| After silence | Payment checking waits; `settlement_overdue` stays active until money is reported. |

## 5. After a decision: payment, disagreement and escalation

| Question | Answer |
|---|---|
| What triggers it? | A payment notice (connector or letter), a bank statement upload, or the user starting a dispute. |
| What does the user want? | The right money in the bank, or the remaining amount challenged. |
| What context is needed? | The approved amount, the settlement letter (amount, UTR, date), the bank credits, the dispute history and its dates. |
| What can run now? | P1 matches the credit by UTR or amount (V-15) and flags short, missing, duplicate or ambiguous credits (V-16). X1 drafts the grievance; `ombudsman_check` opens the Ombudsman route when the insurer rejects the grievance or 30 days pass (V-24). |
| What must wait? | Every letter waits for the user's approval; the user files it and records the date and reference (manual handoff). |
| What can go wrong? | Credit differs from the settlement letter (`payment_mismatch`); a revised decision after payment (`top_up_due`, not a bank error, V-25); filing the Ombudsman complaint too early (refused, V-24); a future filing date (refused, V-23). |
| Who acts next? | The bank pays; the user files with the grievance officer, then the Ombudsman; the insurer revises or upholds. Bank-side errors go to the bank (manual handoff, G1). |
| What proves success? | `payment_verified`: a bank credit matching the settlement (UTR or amount). Cashless: `paid_to_hospital` with the patient share explained (V-17). |
| After success | Checkpoint 6. |
| After failure | `payment_mismatch` with the shortfall; dispute route offered; the case stays open. |
| After silence | Grievance: a 14-day reminder (V-23). Ombudsman eligibility opens after 30 days without a reply (V-24). |

## 6. After resolution: retain, delete or carry forward

| Question | Answer |
|---|---|
| What triggers it? | Payment verified, or a dispute closed by a revised decision whose payment is verified. |
| What does the user want? | Proof of what happened, kept for later, and no data kept longer than they want. |
| What context is needed? | The case file: documents with sources and versions, approvals bound to hashes, the audit of authority and button actions, claims history across rounds. |
| What can run now? | Export of the pack (PDF, EML). The user can delete one document (purged from current and earlier checkpoints, file removed) or the whole session (checkpoints, files and webhook lookup) (built, APP-043). |
| What must wait? | Nothing. |
| What can go wrong? | A later insurer letter, a revised decision or a bank reversal after the case looked closed (see reopening below). |
| Who acts next? | The user. |
| What proves success? | The verified payment with its evidence stays on file until the user deletes it. |
| After success | Case kept as evidence. |
| After failure | Not applicable. |
| After silence | Kept. **Proposed:** a retention period and reuse of confirmed policy facts and authority for the next claim; today each claim is a new thread and nothing is carried across cycles automatically. |

## Completion definitions

| Unit | Complete when | Not complete when |
|---|---|---|
| Submitted item | The payer's claim id is read back or found by the client reference (connected), or the user records the filing date (manual, labelled recorded) | The send returned an error or no answer; it stays `unconfirmed` until a lookup confirms it |
| Answered request | The payer shows the query answered and the stage returns to `submitted` (connected), or the user records the reply date (manual) | A reply is drafted or approved but not sent |
| Decision | A decision with outcome, approved amount, deductions and cited clauses is on file and classified | Only a portal status ("closed", "settled") without the letter |
| Payment | A bank credit matches the settlement by UTR or amount (`payment_verified`); cashless: paid to the hospital with the patient share explained | Only a settlement letter or portal status (`payment_reported`); a short, missing or duplicate credit |
| Resolved dispute | A revised decision is on file and its payment, including any top-up, is verified | A grievance or complaint filed with no reply; a revised decision whose top-up has not arrived |

## Legitimate reopening

A closed-looking case reopens only the part the new evidence touches. Documents, approvals and the submission stay as they are unless that evidence changes them.

| New evidence | What reopens | What stays | Evidence |
|---|---|---|---|
| A new query after submission | Query and reply; stage `query_raised` | Pack, submission, claim id | V-12, V-13 |
| A revised decision after payment | Decision and payment check; `top_up_due` | Documents, submission, earlier payment | V-25 |
| A partial decision on the first policy | A balance claim on the second policy (round 2); first round archived and enclosed | First round's letters and decision | V-22 |
| A credit that differs from the letter | Payment check (`payment_mismatch`); dispute route | Decision | V-16 |
| A corrected document before submission | Pack approval (`approval_invalidated`) | Other documents | V-07, V-18 |
| Withdrawn or expired authority | All writes blocked; approval cleared | Case file and history | V-20 |

---

Previous: [Sources](../02-research/sources.md) | [Index](../../README.md) | Next: [Branch matrix](branch-matrix.md)
