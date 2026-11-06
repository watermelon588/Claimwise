# Architecture graphs

Status: built and checked against the running prototype on 2026-11-06 (session 037, live end-to-end run J1 to J12).
All five graphs describe the synthetic-data prototype. They are not a production design. Real insurer, TPA, bank and grievance access is still manual handoff or unverified (see G1).

| Graph | What it answers | Page | Editable source | Export |
|---|---|---|---|---|
| G1 Product context | Who is involved, what Claimwise replaces, trust and authorization boundaries, how each integration is reached | [g1-product-context.md](g1-product-context.md) | [g1-product-context.excalidraw](../diagrams/src/g1-product-context.excalidraw) | [svg](../diagrams/export/g1-product-context.svg) |
| G2 Lifecycle and state | Onboarding, claim stage, every write (proposed, approved, attempted, confirmed), dispute; pauses, invalidation, reopening | [g2-lifecycle-state.md](g2-lifecycle-state.md) | [g2-lifecycle-and-state.excalidraw](../diagrams/src/g2-lifecycle-and-state.excalidraw) | [svg](../diagrams/export/g2-lifecycle-and-state.svg) |
| G3 Function execution | The agent graph: named nodes, routes, pauses, tools and the API that drives them | [g3-function-execution.md](g3-function-execution.md) | [g3-agent-graph.excalidraw](../diagrams/src/g3-agent-graph.excalidraw) | [svg](../diagrams/export/g3-agent-graph.svg) |
| G4 Sequence and recovery | One claim from upload to verified payment, including a submission the payer accepted but whose answer was lost | [g4-sequence-recovery.md](g4-sequence-recovery.md) | [g4-sequence-and-recovery.excalidraw](../diagrams/src/g4-sequence-and-recovery.excalidraw) | [svg](../diagrams/export/g4-sequence-and-recovery.svg) |
| G5 Data and context | Where each fact comes from, who owns it, where it is stored, what the model sees, versions, corrections, retention | [g5-data-context.md](g5-data-context.md) | [g5-data-and-context.excalidraw](../diagrams/src/g5-data-and-context.excalidraw) | [svg](../diagrams/export/g5-data-and-context.svg) |

Read G1 first for the overview, then G3 for the execution overview. G2, G4 and G5 are the subflows.

## Editing the graphs

- G1 is drawn by hand. Open the `.excalidraw` file at excalidraw.com (File, Open), edit, then export the SVG to `docs/diagrams/export/`.
- G2 to G5 are generated from one layout each by [make_graphs.py](../diagrams/make_graphs.py), which writes both the `.excalidraw` source and the SVG. Run `python docs/diagrams/make_graphs.py` from the repository root. Change the layout in the script, not in Excalidraw, or the next run overwrites the edit.

## Shared legend

| Colour or line | Meaning |
|---|---|
| Blue fill | A model call (O1 reading a file, I1 classifying a message, A1 writing a reply) |
| Grey fill | Deterministic Python |
| Orange fill | A pause: the run stops until a person answers |
| Green fill | Tools, or a confirmed outcome |
| Red fill | Failed, blocked or needs attention; in G5, data never shared |
| Yellow fill | The API or a system outside Claimwise |
| Purple fill (G5) | Stored data |
| Teal fill (G3) | Changed in the current version |
| Solid arrow | A call or a state change, labelled with the data or condition |
| Dashed arrow | A response, an optional path, or the end of a run |

## Function ids

The same ids are used in all graphs, the code comments and the [function catalogue](../05-technical/function-catalogue.md).

| Id | Node or function | Kind | Code |
|---|---|---|---|
| M1 | sync_connector: settle an unconfirmed submission, read the submitted claim, raise and resolve reminders | Deterministic | `backend/app/agent/monitor.py` |
| O1 | parse_new_documents: read each new file into a type and facts; detect versions | Model (structured output) | `backend/app/agent/onboarding.py` |
| O2 | check_onboarding: what is still missing, including caregiver authority | Deterministic | `backend/app/agent/onboarding.py` |
| O3 | confirm_facts: pause for the user to confirm or correct policy facts | Human | `backend/app/agent/onboarding.py` |
| C1 | review_claim: checklist, issues, stage, pack hash, query and decision reading, reminders | Deterministic | `backend/app/agent/claim.py`, `graph.py` |
| P1 | verify_payment: settlement against bank credits, top-up after a revised decision | Deterministic | `backend/app/agent/payment.py` |
| X1 | run_action: every button (pack, submit, record, versions, policy choice, balance claim, grievance, Ombudsman, query reply) | Deterministic, with approval pauses | `backend/app/agent/actions.py`, `submission.py`, `grievance.py` |
| I1 | classify_intent: is the typed message about the claim | Model (structured output) | `backend/app/agent/intent.py` |
| R1 | reply_off_topic: fixed reply, no state change | Deterministic | `backend/app/agent/intent.py` |
| A1 | agent: the reply, ending with the next step | Model | `backend/app/agent/graph.py` |
| T1 | tools: claim_deadline, record_role, update_claim, prepare_submission | Deterministic tools the model may call | `backend/app/agent/tools.py` |

## Orchestration boundary

| Layer | Owns | Does not own |
|---|---|---|
| Web app (React) | Showing state, collecting choices and files, holding this browser's thread ids | Any decision, calculation or call to an insurer |
| API (FastAPI) | Input validation at the trust boundary, one run per thread at a time, resuming pauses, webhook signatures, file storage | Claim logic |
| Agent graph (LangGraph) | Turn order, checkpoints, pauses and resume | Calculations (delegated to deterministic functions) |
| Deterministic Python | Every amount, date, deadline, stage, block, idempotency key and write to the insurer | Wording of replies |
| Model | Reading uploaded files into structured facts (O1), classifying a message (I1), wording the reply and choosing a tool (A1) | Amounts, dates, eligibility, stage, or any write to the insurer |
| Retrieval | No vector search in the prototype. Facts come from the user's files, the connected account (M1) and rule tables in code (deadlines, required documents, Ombudsman limits) | Unverified web text |
| Human | Confirming policy facts, approving the pack and every letter or query reply before it is sent, choosing between versions and policies | Nothing is sent without this step |
| Connector gateway | Per-case consent per tool, the server key, provenance of every record | Claim decisions |

## Execution properties shown in the graphs

- Parallel steps and joins: none inside a turn. Each turn runs the nodes in order (G3). Separate threads run independently, and the same thread never runs twice at once (per-thread lock in the API).
- Pauses: O3 confirm policy, approve pack, approve letter or query reply. A pause is saved in the checkpoint and survives a restart (G2, G4).
- Timers: none run in the background. Deadlines and reminders are dated rules, checked whenever the thread is opened or a webhook arrives (M1, C1).
- Retries: chat and classification calls fall back from Gemini to Groq; document reading is Gemini only (Groq takes no files), so a failed read marks the document failed. Every model call gives up after 60 seconds and two retries. A submission is never retried blind: the payer is asked for the client reference first, and the same idempotency key always returns the same claim (G4).
- Failure exits: unconfirmed, refused, connection expired, blocked by authority, parse failed (G2 lane C, G4 panels).

## How the graphs were checked

Each graph was compared with the code (`graph.py`, `state.py`, `routes.py`) and with the live run recorded in [validation-plan.md](../07-delivery/validation-plan.md). Graph statements that the run exercised carry the spec id (for example V-10 for the single claim after a lost answer, V-34 for a pause surviving a restart).
