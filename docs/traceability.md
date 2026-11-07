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
| R-08 | Sensitive records and family authority built into the workflow | [Product brief](01-product-brief.md), [permissions](05-technical/actions-permissions-and-data.md), [G5](04-architecture/g5-data-context.md) | Draft |
| R-09 | Vision plus a first release marked executes / coordinates through a human / deferred | [First-release scope](01-product-brief.md#proposed-first-release) | Draft proposal |

## Page 2: Research

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-10 | Six research angles investigated | [Six research angles](02-research/evidence-register.md#4-the-six-research-angles) | Draft |
| R-11 | At least 3 different user situations from firsthand sources, including follow-up replies | [Situation register](02-research/evidence-register.md#1-situation-register) | Draft |
| R-12 | At least 3 alternatives including a manual workaround | [Alternatives](02-research/alternatives.md) | Draft |
| R-13 | Facts, repeated patterns and hypotheses separated | [Evidence register](02-research/evidence-register.md) | Draft |
| R-14 | Register fields: source/date, segment, trigger, workaround, consequence, existing solution, remaining gap | [Situation register](02-research/evidence-register.md#1-situation-register) | Draft |
| R-15 | Access limits identified | [Access limits](02-research/evidence-register.md#6-access-limits) | Draft |
| R-16 | Contradictory evidence identified | [Contradictory evidence](02-research/evidence-register.md#5-contradictory-evidence) | Draft |
| R-17 | At least one reason the agent may not be worth building | [Reasons to reconsider](02-research/evidence-register.md#8-reasons-the-agent-may-not-be-worth-building) | Draft |
| R-18 | No market-size or willingness-to-pay claim without evidence | [Evidence register](02-research/evidence-register.md#what-is-not-claimed) | Draft |

## Page 3: Journey, branches and completion

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-19 | Six checkpoints: before, during, waiting, decision, after decision, after resolution | [Lifecycle map](03-lifecycle/lifecycle-map.md) | Draft |
| R-20 | Per-stage questions: trigger, want, context, what runs now, what must wait, failure, next actor, proof of success, after success / failure / silence | [Lifecycle map](03-lifecycle/lifecycle-map.md) | Draft |
| R-21 | Branch challenge 1: a document requested again under a different name | [Branch matrix](03-lifecycle/branch-matrix.md) | Draft; repeated request exercised |
| R-22 | Branch challenge 2: partial settlement with a payment that does not match | [Branch matrix](03-lifecycle/branch-matrix.md), [research gaps](02-research/evidence-register.md#9-gaps) | Draft scenario; exact firsthand evidence gap |
| R-23 | Branch challenge 3: caregiver consent changes while a second policy is relevant | [Branch matrix](03-lifecycle/branch-matrix.md), [research gaps](02-research/evidence-register.md#9-gaps) | Draft scenario; exact firsthand evidence gap |
| R-24 | Completion defined for an item, a request, a decision, a payment and a dispute | [Completion definitions](03-lifecycle/lifecycle-map.md#completion-definitions) | Draft |
| R-25 | Legitimate reopening | [Legitimate reopening](03-lifecycle/lifecycle-map.md#legitimate-reopening) | Draft |
| R-26 | At least 5 paths (standard, missing or contradictory, change of mind, external delay or failure, post-completion) plus domain paths, all rejoining one agent | [Branch matrix](03-lifecycle/branch-matrix.md) | Draft |

## Page 4: Product and architecture graphs

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-27 | G1 product context: trust boundaries, integrations labelled documented / partner-only / manual handoff / unverified | [G1 product context](04-architecture/g1-product-context.md), [editable source](diagrams/src/g1-product-context.excalidraw) | Draft (diagram) |
| R-28 | G2 lifecycle and state: proposed, approved, attempted, confirmed; interruption and resume | [G2 lifecycle and state](04-architecture/g2-lifecycle-state.md) | Draft graph with prototype evidence |
| R-29 | G3 function execution: named functions, data-labelled edges, parallel steps, joins, pauses, timers, retries, failure exits | [G3 function execution](04-architecture/g3-function-execution.md), [editable source](diagrams/src/g3-agent-graph.excalidraw) | Draft graph with prototype evidence |
| R-30 | G4 sequence and recovery: one full journey plus reconciling a response that was accepted but lost | [G4 sequence and recovery](04-architecture/g4-sequence-recovery.md) | Draft graph; recovery verified in V-10 |
| R-31 | G5 data and context: ownership, provenance, versions, retention, correction propagation, approval invalidation | [G5 data and context](04-architecture/g5-data-context.md) | Draft graph; production retention pending |
| R-32 | Orchestration boundary; deterministic vs retrieval vs model vs human | [Orchestration boundary](04-architecture/README.md#orchestration-boundary) | Draft |
| R-33 | Readable graphs: function IDs, legend, labelled arrows, overview plus subflows, editable sources, readable exports, index | [Graph index and legend](04-architecture/README.md), [editable sources](diagrams/src/), [exports](diagrams/export/) | Draft graph set |

## Page 5: Low-level technical sheet

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-34 | Contract fields for every function | [Function catalogue](05-technical/function-catalogue.md) | Draft contracts and implementation index |
| R-35 | Per API or tool: provider, operation, docs link, auth, schemas, quotas, cost, access evidence, untested items, fallback; internal routes labelled proposed | [API and tool matrix](05-technical/api-tool-matrix.md) | Draft |
| R-36 | Models and retrieval: why, inputs, output schema, rejection of unsupported claims, citations, confidence, escalation, calculations never delegated to a model | [Models and retrieval](05-technical/models-and-retrieval.md) | Draft |
| R-37 | Execution and memory: queue, per-user concurrency, joins, version checks, deduplication, crash recovery, long waits, selective reopening | [Execution and memory](05-technical/execution-and-memory.md) | Draft |
| R-38 | Actions and personal data: consequence classes, consent, delegated authority, recipient validation, approval, audit, revocation, fetched text as data, tenancy, secrets, retention, deletion | [Actions, permissions and data](05-technical/actions-permissions-and-data.md) | Draft |
| R-39 | UX screens: onboarding, goal, progress, needs input, comparison, approval, outcome, correction without restart | [UX sketches](06-experience/ux-sketches.md) | Draft |
| R-40 | Appendix: schemas, function catalogue, API/tool matrix, state transitions, error catalogue, payloads, cost model, measurement plan, milestones | [Technical appendix](05-technical/README.md), [function contracts](05-technical/function-catalogue.md), [G2](04-architecture/g2-lifecycle-state.md), [worked cost estimate](07-delivery/feasibility-and-rollout.md#worked-model-cost-estimate) | Draft |
| R-41 | Justified technology stack | [Stack rationale](05-technical/README.md#stack-and-rationale) | Draft |

## Page 8: Submission and evaluation

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-42 | Artifact 1: product brief and evidence register | [Product brief](01-product-brief.md), [evidence register](02-research/evidence-register.md) | Draft |
| R-43 | Artifact 2: persona/situation matrix, lifecycle map, branch matrix | [Personas](02-research/personas-and-situations.md), [lifecycle](03-lifecycle/lifecycle-map.md), [branches](03-lifecycle/branch-matrix.md) | Draft |
| R-44 | Artifact 3: the five graphs with editable sources | [Five graphs and editable sources](04-architecture/README.md) | Draft graph set |
| R-45 | Artifact 4: low-level technical documentation and example payloads | [Technical reference](05-technical/README.md), [functions](05-technical/function-catalogue.md), [schemas and payloads](05-technical/schemas.md) | Draft |
| R-46 | Artifact 5: UX sketches, validation plan, phased implementation plan | [UX sketches](06-experience/ux-sketches.md), [validation](07-delivery/validation-plan.md), [implementation plan](07-delivery/implementation-plan.md) | Draft; historical results recorded |
| R-47 | Artifact 6: short walkthrough of one goal across stages and alternate outcomes | [Written walkthrough](07-delivery/demo-walkthrough.md), [journeys](06-experience/journeys.md) | Written walkthrough available; recording open |
| R-48 | Three complete journeys (standard, different user situation, failure or disagreement into follow-up), one continuing past the first apparent success | [Three journeys](06-experience/journeys.md) | Historical runs documented; final top-up verification is a specification |
| R-49 | At least 12 validation cases with expected outcomes, including malicious source text that must not authorize an action; untested cases labelled as specifications | [Validation plan and results](07-delivery/validation-plan.md) | 37 specs exercised in historical run; three live checks open |
| R-50 | Feasibility and rollout: vision vs first release, integration proof, unresolved access, human handoffs, effort, costs, pilot with outcome and failure metrics, stop / recover / roll back | [Feasibility and rollout](07-delivery/feasibility-and-rollout.md) | Draft with worked model estimate; pilot unapproved |
| R-51 | None of the not-acceptable items (one anecdote, digest as product, graph ending at "generate report", invented API access, unlabelled assumptions, unrelated features, no persistence or proof of completion) | [Submission map](../submission/claimwise-design.pdf), [scope and access limits](decisions.md) | Design coverage checked; owner review open |

## Project owner requirements

| R-ID | Requirement | File | Status |
|---|---|---|---|
| R-52 | Consolidated PDF of the design documents | [Consolidated design PDF](../submission/claimwise-design.pdf) | Draft assembled; owner review open |
| R-53 | Walkthrough video with links to editable sources | [Walkthrough script](07-delivery/demo-walkthrough.md) | Recording open |

---

Previous: [Hosting the Claimwise demo](07-delivery/hosting.md) | [Index](../README.md) | Next: [Decisions and assumptions](decisions.md)
