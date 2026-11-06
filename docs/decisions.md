# Decisions and assumptions

Every decision that shapes the design, every assumption it rests on, and every question still open. A decision moves from Open to Approved only when the project owner approves it.

## Decisions

| ID | Date | Decision | Status |
|---|---|---|---|
| D-01 | 2026-11-04 | The repository is public. The submission is this repository plus a consolidated PDF and a walkthrough video, with links to editable sources. | Approved |
| D-02 | 2026-11-04 | Treat the frontend, backend, database and agent as one prototype deliverable. | Approved |
| D-03 | 2026-11-04 | Review the documentation in dependency order. The build and documentation may proceed in parallel under D-06. | Approved |
| D-04 | 2026-11-04 | Research source files (the brief, regulator PDFs, saved case threads) are not committed. Sources are cited by public URL in [sources](02-research/sources.md). Usernames and personal details from case threads are not reproduced. | Approved |
| D-05 | 2026-11-04 | All examples, payloads and test data are synthetic. | Approved |
| D-06 | 2026-11-04 | Start the prototype build while the documentation and scope review continue. | Approved |
| D-07 | 2026-11-04 | Use FastAPI and LangGraph for the prototype, React for the workspace, and Neon for persistent checkpoints. Gemini is the default text provider, with Groq as the configured fallback. [Stack rationale](05-technical/README.md) | Approved prototype stack |
| D-08 | 2026-11-06 | Prepare a manual Vercel frontend preview. The Python hosting options and actual service URLs are separate deployment decisions. [Deployment guide](../frontend/DEPLOYMENT.md) | Approved preparation |

## Assumptions

| ID | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| AS-01 | The product targets India. | Every source and case found is Indian. Not yet an approved scope decision (see OQ-01). | Regulatory facts and routes would need replacing. |
| AS-02 | Timers in the prototype use published source texts and demo rules. | The full amendment history and case-specific eligibility have yet to be verified. | Real-case deadlines and rights require current official confirmation. |
| AS-03 | Claimwise has no verified live claimant-side API access for insurers, TPAs, NHCX or Bima Bharosa. | Public portal and protocol documentation was found. Credentials, permission and partner access remain unverified. | Manual handoff stays the available release route until access is proven. |
| AS-04 | Forum cases show real failure modes but over-represent problems. | Selection bias of complaint threads; contradictory evidence recorded. | Severity or frequency could be overstated. |

## Open questions

Review these decisions against the [draft product brief](01-product-brief.md). The prototype's implemented options provide evidence for the review.

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
