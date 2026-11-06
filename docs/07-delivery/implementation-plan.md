# Phased implementation plan

**Status:** Draft implementation and handoff record. The steps describe the prototype as one deliverable. Scope decisions for a real release remain open. [Decisions](../decisions.md)

| Milestone | Prototype outcome | Evidence location |
| --- | --- | --- |
| Foundation | FastAPI API, LangGraph checkpointer, React Dossier, mock services and gateway. | [Technical reference](../05-technical/README.md) · [Run locally](../../README.md#run-locally) |
| 1. Evidence and pack | Reject unrelated uploads, review and export a pack, track progress and reconcile statements. | [Document parsing](../../backend/app/agent/onboarding.py) · [Pack exports](../../backend/app/agent/pack_export.py) · [Payment checks](../../backend/app/agent/payment.py) |
| 2. Guided turns | Derive next actions from state and handle off-topic text without treating it as a claim action. | [Action routing](../../backend/app/agent/actions.py) · [Intent routing](../../backend/app/agent/intent.py) |
| 3. Submission and monitoring | Use a human handoff or an approved mock submission. Recover uncertain outcomes, read mock status and show notifications. | [Connector guide](../05-technical/provider-connectors.md) · [Execution and memory](../05-technical/execution-and-memory.md) |
| 4. Domain extensions | Version evidence, support multiple policies and caregiver authority, prepare disputes and reopen an affected check. | [Case state](../../backend/app/agent/state.py) · [UX sketches](../06-experience/ux-sketches.md) |
| Packaging | Frontend preview setup prepared for manual Vercel upload. Services and upstream URLs are deployment inputs. | [Deployment setup](../../frontend/DEPLOYMENT.md) |

## Remaining work by release decision

1. Review the scope and research assumptions. Finish the separate architecture, function, journey and validation packages and link them from the repository index.
2. Assemble the synthetic demonstration. Confirm the live preview inputs, run a reproducible release check, and compile the final PDF and walkthrough after content review.
3. Before a real-user pilot, verify identity and data access, provider agreements, audit and retention, and operational controls. Start with the approved manual routes and enable a live action only after its authorization, receipts and recovery are proven. [Rollout gates](feasibility-and-rollout.md)

---

Previous: [UX sketches](../06-experience/ux-sketches.md) | [Index](../../README.md) | Next: [Feasibility and rollout](feasibility-and-rollout.md)
