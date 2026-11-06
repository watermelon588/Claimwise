# Actions, permissions and data

**Status:** Draft design and implementation reference. The current guest workspace and mock controls are for synthetic records. The separate validation workstream covers vulnerability findings and test results.

## Decision rights

| Action | Required authority | Current handling |
| --- | --- | --- |
| Inspect a supplied file or compare facts | Case user or authorized representative | Read the file and surface evidence and missing fields. User confirms policy details. |
| Read mock provider records | Per-case provider grant | Server-side gateway bearer credential and current grant. Revocation blocks a subsequent read or write. |
| Export a pack or letter draft | Case user | Exports are for review or human handoff. User verifies the recipient and attachments before sending. |
| Submit to the mock payer | Current pack approval, active TPA grant, and caregiver scope when applicable | Deterministic submit gate and idempotency key. Payer also checks the representative against its own records. |
| File a grievance or Ombudsman complaint | Appropriate human claimant or representative | Draft, approve, then file through the official channel. Claimwise records the reference supplied by the user. |
| Withdraw authority or disconnect | Demo case user | Withdrawal invalidates approval and blocks actions that depend on it. Gateway revocation and local unlink are distinct actions. |

[Authority checks](../../backend/app/agent/authority.py) · [Submission gate](../../backend/app/agent/submission.py) · [Connector consent](provider-connectors.md) · [Public handoff sources](../02-research/sources.md)

## Ownership and data handling

| Data | Prototype storage and visibility | Real-user design requirement |
| --- | --- | --- |
| Original uploads | Server file storage, keyed by thread and document IDs. Pack originals are served through a dedicated route. | Verified access, encryption, purpose-limited retention, export and deletion. |
| Case state and evidence facts | LangGraph checkpoints, with a public thread response projection. | Per-user and per-case authorization. Separate patient, caregiver, household and claim-specific fields. |
| Browser history and file preview | Local session summaries and active thread ID. Original previews in the document modal can depend on the current tab. | Document what persists on a shared device, and give the user control over local history. |
| Mock provider data and credentials | SQLite and generated files in the mock service. Provider grants in the gateway process. Server keys supplied via configuration. | Separate synthetic data from live data and keep credentials server-side. Verify retention, revocation and audit requirements with each provider. |
| Audit record | Claim-level record of actor, action, time and detail in the checkpoint. | Verify identity independently and define durable audit storage and access policy. |

The prototype has separate deletion surfaces for checkpoints, uploaded files, browser history and mock records. Production retention periods and an authenticated deletion workflow are pending decisions. Files and provider text are input data and cannot provide authority. [Schemas](schemas.md) · [Rollout gates](../07-delivery/feasibility-and-rollout.md)

---

Previous: [Execution and memory](execution-and-memory.md) | [Index](../../README.md) | Next: [UX sketches](../06-experience/ux-sketches.md)
