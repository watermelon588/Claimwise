# Branch matrix

Status: Draft, 2026-11-08. Each path is tied to a live journey (J) and validation spec (V) in [validation-plan.md](../07-delivery/validation-plan.md). A combination that was not run as one journey is labelled **Specification (not run)** and lists the tested parts it is made of. Checkpoints refer to the [lifecycle map](lifecycle-map.md).

## How every path shares context and rejoins one agent

- **One thread, one checkpoint.** A claim is one LangGraph thread. Documents, policies, role and authority, claim info, submission, dispute and notifications live in its checkpoint ([G5](../04-architecture/g5-data-context.md)). No path keeps a private copy.
- **Derived, not stored.** Stage and payment status are recomputed every turn by C1 and P1 from the evidence on file, so a branch cannot leave the case in a stale stage.
- **One entry point.** Every upload, message, button, webhook and thread open runs the same graph: M1, O1, O2, C1, P1, then the route to X1, I1 or A1 ([G3](../04-architecture/g3-function-execution.md)). A branch ends by writing state; the next turn picks it up from there.
- **One approval rule.** Every write to an insurer goes proposed, approved (hash bound), attempted, confirmed ([G2](../04-architecture/g2-lifecycle-state.md) lane C), whichever path reached it.

## Branch challenges from the brief

### 1. The same hospital document is requested again under another name, sent twice, never acknowledged

| Aspect | Handling |
|---|---|
| Detection | C1 matches each requested item by document type, not by its label, against documents held before the query. "Discharge Card" maps to the discharge summary already sent, so it is flagged as a repeat with the earlier file and date (`repeated_request`, V-12). |
| Reply | X1 drafts a reply that lists what was already sent and when; only genuinely new items are asked for (V-12, V-13). |
| Acknowledgement, connected route | Sending is confirmed only when the payer shows the query answered (V-13). An unanswered send stays visibly open; it is not marked done. |
| Acknowledgement, manual route | The user records the date they sent it, labelled recorded. **Gap:** there is no explicit "no acknowledgement" chase reminder for manual replies; the settlement-overdue reminder still fires (V-32). **Proposed:** a dated reminder to ask the insurer for written acknowledgement. |
| Rejoin | Checkpoint 3; stage returns to `submitted` once answered. |

### 2. Partial settlement; portal shows closed; the bank credit differs from the letter; the user challenges the rest

| Aspect | Handling |
|---|---|
| Portal says closed | Not a completion signal. Completion needs the decision letter and a matching bank credit (lifecycle map, completion definitions). |
| Partial decision | C1 compares the decision line by line and flags deductions without a clause (V-14). |
| Credit differs from the letter | P1 compares the bank credit with the settlement amount and UTR: short or missing credit gives `payment_mismatch` with the shortfall (V-16, J7). |
| Challenge the remainder | Dispute route: grievance letter approved by the user, filing date recorded, 14-day reminder (V-23); Ombudsman when eligible (V-24). |
| Revised decision | Reopens only the decision and payment check; the extra is a top-up due, not a bank error (V-25). |
| Bank-side error | If the insurer paid correctly but the bank credited less, it is a bank matter (RBI route, manual handoff in [G1](../04-architecture/g1-product-context.md)). Claimwise shows the evidence; it does not file with the bank. |
| Evidence status | Each part ran live (V-14, V-16, V-23 to V-25). The full combination in one claim is **Specification (not run)**. Firsthand evidence for this exact situation is thin ([evidence register](../02-research/evidence-register.md)). |
| Rejoin | Checkpoint 5; complete when the top-up credit matches. |

### 3. A caregiver manages a parent's records, consent changes mid-case, another policy may apply

| Aspect | Handling |
|---|---|
| Authority | The caregiver records authority with scope and expiry; it is checked against the uploaded proof (wrong name refused, V-19). |
| Consent withdrawn | Approval is cleared and every write is blocked until authority is recorded again (V-20). The case file stays. |
| Consent narrowed or expired | Writes outside the scope or after expiry are blocked (G2 lane C). |
| Second policy | Both policies are confirmed; the claimant chooses which to claim first; the pack is blocked until they do (V-22). After the first decision, a balance claim on the other policy starts round 2. |
| Payer does not recognise the caregiver | Refusal shown with its reason, no retry, connection kept (V-21). |
| Evidence status | Each part ran live (J2, J3, J4). Consent changing while a second policy is pending, in one claim, is **Specification (not run)**. |
| Rejoin | Checkpoint 1 (authority, policy choice) or 2 (submission), depending on when consent changes. |

## Paths

| # | Path | Kind | Trigger | What Claimwise does | Proof | Rejoins at | Evidence |
|---|---|---|---|---|---|---|---|
| P1 | Standard reimbursement | Required: standard | Patient uploads, approves, submits through the connector | Reads, checks, pack, submit, monitor, verify credit | `payment_verified` by UTR | End | J1, V-01 to V-15 |
| P2 | Missing or contradictory information | Required | A required document is missing; names, dates or totals disagree; an unrelated file | Lists what is missing, raises the issue, rejects unrelated files; blocks the pack | Issue codes; `missing` list | Checkpoint 1 | V-03, V-04, V-05 |
| P3 | Renamed repeat request | Required: missing / contradictory | Insurer asks again for a document already sent | Flags the repeat with date; reply lists what was sent | `repeated_request`; query answered | Checkpoint 3 | J5, V-12, V-13 |
| P4 | User changes their mind | Required: change of mind | Corrects a policy fact, replaces a document, declines or withdraws consent | Recomputes downstream; approval goes stale; writes blocked when consent is withdrawn | `approval_invalidated`; version 2; submit refused | Checkpoint 1 | V-02, V-07, V-18, V-20 |
| P5 | Answer lost after the payer accepted | Required: external failure | Payer saves the claim, the answer is lost | Lookup by reference, adopts the claim, never resends | One claim at the payer | Checkpoint 2 | J6, V-10 |
| P6 | Payer outage or delay | Required: external delay | Payer down; no payment by the due date | Marks unconfirmed; turn completes; overdue reminder | `unconfirmed`; `settlement_overdue` | Checkpoint 2 or 3 | J6, V-32, V-36 |
| P7 | Revised decision after payment | Required: post-completion | Dispute wins after the first payment | Reopens decision and payment only; top-up due | `top_up_due`; then verified on the next credit (**Specification (not run)**) | Checkpoint 5 | J2, V-25 |
| P8 | Credit short or missing | Domain | Bank credit differs from the settlement | Flags the shortfall; offers the dispute route | `payment_mismatch` | Checkpoint 5 | J7, V-16 |
| P9 | Dispute ladder | Domain | Partial or rejected decision | Grievance, then Ombudsman when eligible; every letter approved by the user | Filing dates; reminders | Checkpoint 5 | J2, V-23, V-24 |
| P10 | Household with two policies | Domain | Patient covered by two policies | Claimant chooses; balance claim on the second policy | Second claim for the balance only | Checkpoint 1, round 2 | J3, V-22 |
| P11 | Caregiver acting for a parent | Domain | Caregiver is not the policyholder | Authority with proof, scope and expiry; acting user sent to the payer | Payer accepts the acting user | Checkpoint 1 | J2, V-19, V-09 |
| P12 | Representative refused by the payer | Domain | Payer does not recognise the caregiver | Shows the reason, keeps the connection, no retry | `refused` with reason | Checkpoint 2 | J4, V-21 |
| P13 | Cashless claim | Domain | Hospital is paid directly | No bank credit expected; patient share explained | `paid_to_hospital` | Checkpoint 5 | J8, V-17 |
| P14 | No connection: manual route | Domain | The user files on the portal or by post | Records dates; starts the 15-day clock; reads uploaded letters | Recorded dates; stage from evidence | Checkpoint 2 | J7, V-33 |
| P15 | Hostile text in a document or chat | Domain | A letter or message contains instructions | Treated as data; nothing approved or sent | No state change beyond reading | Any | J7, J9, V-26, V-27 |

Paths P1 to P7 cover the five required kinds (standard; missing or contradictory; change of mind; external delay or failure; post-completion follow-up). P8 to P15 are domain paths from the research and the build.

---

Previous: [Lifecycle map](lifecycle-map.md) | [Index](../../README.md) | Next: [Architecture graphs](../04-architecture/README.md)
