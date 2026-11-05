# Traceability

Every requirement in the assignment brief (S-01), with the file that satisfies it and its status. This is the checklist used before submission.

Status: **Planned** (file not written), **Draft** (written, not reviewed), **Reviewed** (approved by the project owner), **Gap** (written, but evidence or content is knowingly incomplete).

## Page 1: Product framing

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-01 | One lifecycle agent serving a patient, an authorized caregiver and a household with more than one cover | [Product brief](01-product-brief.md) | Draft |
| R-02 | Designed for a class of users, not one anecdote | [Personas](02-research/personas-and-situations.md), [product brief](01-product-brief.md) | Draft |
| R-03 | More than a summarizer, letter writer or document folder | [Product brief](01-product-brief.md), [alternatives](02-research/alternatives.md) | Draft |
| R-04 | Name the category of app the product replaces | [Product brief](01-product-brief.md) | Draft |
| R-05 | How users set goals, delegate, see progress, resolve uncertainty, approve and confirm | [Product brief](01-product-brief.md), [UX sketches](06-experience/ux-sketches.md) | Draft |
| R-06 | Chosen jurisdictions, claim routes and specialist handoffs | [Scope decisions](decisions.md#open-questions), [product brief](01-product-brief.md#proposed-first-release) | Draft proposal; approval open |
| R-07 | Administrative help kept separate from medical and legal advice | [Product brief](01-product-brief.md), [permissions](05-technical/actions-permissions-and-data.md) | Draft |
| R-08 | Sensitive records and family authority built into the workflow | [Product brief](01-product-brief.md), [permissions and data](05-technical/actions-permissions-and-data.md); G5 planned | Draft text; graph pending |
| R-09 | Vision plus a first release marked executes / coordinates through a human / deferred | [First-release scope](01-product-brief.md#proposed-first-release) | Draft proposal |

## Page 2: Research

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-10 | Six research angles investigated | 02-research/evidence-register.md, section 4 | Draft |
| R-11 | At least 3 different user situations from firsthand sources, including follow-up replies | 02-research/evidence-register.md, section 1 | Draft |
| R-12 | At least 3 alternatives including a manual workaround | 02-research/alternatives.md | Draft |
| R-13 | Facts, repeated patterns and hypotheses separated | 02-research/evidence-register.md, sections 1-3 and 7 | Draft |
| R-14 | Register fields: source/date, segment, trigger, workaround, consequence, existing solution, remaining gap | 02-research/evidence-register.md, section 1 | Draft |
| R-15 | Access limits identified | 02-research/evidence-register.md, section 6 | Draft |
| R-16 | Contradictory evidence identified | 02-research/evidence-register.md, section 5 | Draft |
| R-17 | At least one reason the agent may not be worth building | 02-research/evidence-register.md, section 8 | Draft |
| R-18 | No market-size or willingness-to-pay claim without evidence | All research files | Draft |

## Page 3: Journey, branches and completion

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-19 | Six checkpoints: before, during, waiting, decision, after decision, after resolution | 03-lifecycle/lifecycle-map.md | Planned |
| R-20 | Per-stage questions: trigger, want, context, what runs now, what must wait, failure, next actor, proof of success, after success / failure / silence | 03-lifecycle/lifecycle-map.md | Planned |
| R-21 | Branch challenge 1: a document requested again under a different name | 03-lifecycle/branch-matrix.md | Planned |
| R-22 | Branch challenge 2: partial settlement with a payment that does not match | 03-lifecycle/branch-matrix.md | Planned (evidence gap) |
| R-23 | Branch challenge 3: caregiver consent changes while a second policy is relevant | 03-lifecycle/branch-matrix.md | Planned (evidence gap) |
| R-24 | Completion defined for an item, a request, a decision, a payment and a dispute | 03-lifecycle/lifecycle-map.md | Planned |
| R-25 | Legitimate reopening | 03-lifecycle/lifecycle-map.md | Planned |
| R-26 | At least 5 paths (standard, missing or contradictory, change of mind, external delay or failure, post-completion) plus domain paths, all rejoining one agent | 03-lifecycle/branch-matrix.md | Planned |

## Page 4: Product and architecture graphs

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-27 | G1 product context: trust boundaries, integrations labelled documented / partner-only / manual handoff / unverified | 04-architecture/g1-product-context.md; diagrams/src/g1-product-context.excalidraw | Draft (diagram) |
| R-28 | G2 lifecycle and state: proposed, approved, attempted, confirmed; interruption and resume | 04-architecture/g2-lifecycle-state.md | Planned |
| R-29 | G3 function execution: named functions, data-labelled edges, parallel steps, joins, pauses, timers, retries, failure exits | 04-architecture/g3-function-execution.md; diagrams/src/g3-agent-graph.excalidraw | Draft (v0.1, grows with the code) |
| R-30 | G4 sequence and recovery: one full journey plus reconciling a response that was accepted but lost | 04-architecture/g4-sequence-recovery.md | Planned |
| R-31 | G5 data and context: ownership, provenance, versions, retention, correction propagation, approval invalidation | 04-architecture/g5-data-context.md | Planned |
| R-32 | Orchestration boundary; deterministic vs retrieval vs model vs human | 04-architecture/README.md | Planned |
| R-33 | Readable graphs: function IDs, legend, labelled arrows, overview plus subflows, editable sources, readable exports, index | 04-architecture/README.md; diagrams/ | Planned |

## Page 5: Low-level technical sheet

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-34 | Contract fields for every function | 05-technical/function-catalogue.md | Planned |
| R-35 | Per API or tool: provider, operation, docs link, auth, schemas, quotas, cost, access evidence, untested items, fallback; internal routes labelled proposed | [API and tool matrix](05-technical/api-tool-matrix.md) | Draft |
| R-36 | Models and retrieval: why, inputs, output schema, rejection of unsupported claims, citations, confidence, escalation, calculations never delegated to a model | [Models and retrieval](05-technical/models-and-retrieval.md) | Draft |
| R-37 | Execution and memory: queue, per-user concurrency, joins, version checks, deduplication, crash recovery, long waits, selective reopening | [Execution and memory](05-technical/execution-and-memory.md) | Draft |
| R-38 | Actions and personal data: consequence classes, consent, delegated authority, recipient validation, approval, audit, revocation, fetched text as data, tenancy, secrets, retention, deletion | [Actions, permissions and data](05-technical/actions-permissions-and-data.md) | Draft |
| R-39 | UX screens: onboarding, goal, progress, needs input, comparison, approval, outcome, correction without restart | [UX sketches](06-experience/ux-sketches.md) | Draft |
| R-40 | Appendix: schemas, function catalogue, API/tool matrix, state transitions, error catalogue, payloads, cost model, measurement plan, milestones | [Technical appendix](05-technical/README.md) | Partial draft; function and state references pending |
| R-41 | Justified technology stack | [Stack rationale](05-technical/README.md#stack-and-rationale) | Draft |

## Page 8: Submission and evaluation

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-42 | Artifact 1: product brief and evidence register | [Product brief](01-product-brief.md), [evidence register](02-research/evidence-register.md) | Draft |
| R-43 | Artifact 2: persona/situation matrix, lifecycle map, branch matrix | 02-research/personas-and-situations.md; 03-lifecycle/ | Draft / Planned |
| R-44 | Artifact 3: the five graphs with editable sources | 04-architecture/; diagrams/src/ | Planned |
| R-45 | Artifact 4: low-level technical documentation and example payloads | [Technical reference](05-technical/README.md), [schemas and payloads](05-technical/schemas.md) | Partial draft; function catalogue pending |
| R-46 | Artifact 5: UX sketches, validation plan, phased implementation plan | [UX sketches](06-experience/ux-sketches.md), [implementation plan](07-delivery/implementation-plan.md); validation plan pending | Partial draft |
| R-47 | Artifact 6: short walkthrough of one goal across stages and alternate outcomes | 06-experience/journeys.md; video/ | Planned |
| R-48 | Three complete journeys (standard, different user situation, failure or disagreement into follow-up), one continuing past the first apparent success | 06-experience/journeys.md | Planned |
| R-49 | At least 12 validation cases with expected outcomes, including malicious source text that must not authorize an action; untested cases labelled as specifications | 07-delivery/validation-plan.md | Planned |
| R-50 | Feasibility and rollout: vision vs first release, integration proof, unresolved access, human handoffs, effort, costs, pilot with outcome and failure metrics, stop / recover / roll back | [Feasibility and rollout](07-delivery/feasibility-and-rollout.md) | Draft proposal; costs and pilot unmeasured |
| R-51 | None of the not-acceptable items (one anecdote, digest as product, graph ending at "generate report", invented API access, unlabelled assumptions, unrelated features, no persistence or proof of completion) | Final check across all files | Planned |

## Project owner requirements

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-52 | Consolidated PDF of the design documents | submission/claimwise-design.pdf | Planned |
| R-53 | Walkthrough video with links to editable sources | video/ | Planned |

---

Previous: [Index](../README.md) | [Index](../README.md) | Next: [Decisions](decisions.md)
