# Decisions and assumptions

Every decision that shapes the design, every assumption it rests on, and every question still open. A decision moves from Open to Approved only when the project owner approves it.

## Decisions

| ID | Date | Decision | Status |
|---|---|---|---|
| D-01 | 2026-11-04 | The repository is public. The submission is this repository plus a consolidated PDF and a walkthrough video, with links to editable sources. | Approved |
| D-02 | 2026-11-04 | A working prototype is in scope as one deliverable. Its decomposition is decided later, after the lifecycle is approved. | Approved |
| D-03 | 2026-11-04 | Documents are written in dependency order, not page order: research, then scope decisions, then the product brief, then the lifecycle, then design and build, then submission. Each step ends with a review. | Approved |
| D-04 | 2026-11-04 | Research source files (the brief, regulator PDFs, saved case threads) are not committed. Sources are cited by public URL in [sources](02-research/sources.md). Usernames and personal details from case threads are not reproduced. | Approved |
| D-05 | 2026-11-04 | All examples, payloads and test data are synthetic. | Approved |

## Assumptions

| ID | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| AS-01 | The product targets India. | Every source and case found is Indian. Not yet an approved scope decision (see OQ-01). | Regulatory facts and routes would need replacing. |
| AS-02 | The 2024 IRDAI master circulars are still in force as stated. | Published 2024-05-29 and 2024-09-05; reviewed annually; later amendments not checked. | Timers and rights in the design could be out of date. |
| AS-03 | No claimant-side API exists for insurers, TPAs, NHCX or Bima Bharosa. | Limited public search found none. | If one exists, some manual handoffs could become integrations. |
| AS-04 | Forum cases show real failure modes but over-represent problems. | Selection bias of complaint threads; contradictory evidence recorded. | Severity or frequency could be overstated. |

## Open questions

Resolved at the scope review, before the product brief is written.

| ID | Question | Notes |
|---|---|---|
| OQ-01 | Which jurisdiction? | India is assumed (AS-01). |
| OQ-02 | Which users in the first release: patient, caregiver, multi-cover household, or all three? | The assignment asks for all three in the vision. |
| OQ-03 | Which claim routes: cashless, reimbursement, or both? | Evidence shows one event often uses both (PT-07). |
| OQ-04 | Which app category does Claimwise replace? | Candidates come from [alternatives](02-research/alternatives.md). |
| OQ-05 | Which specialist handoffs, and where is the line between administrative, medical and legal help? | Medical necessity (E-08) and legal disputes are outside administrative help. |
| OQ-06 | What does the first release execute, coordinate through a human, or defer? | Constrained by access limits: every integration found is a manual handoff or partner-only. |
| OQ-07 | How are the two evidence gaps handled (bank credit mismatch, consent change mid-case)? | Collect more cases, or design from rules and label as hypotheses. |

---

Previous: [Traceability](traceability.md) | [Index](../README.md) | Next: [Glossary](glossary.md)
