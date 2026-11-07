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

### Current deletion and access

- `DELETE /api/thread/{id}/documents/{document_id}` removes the server upload and historical checkpoint copies of that record. Claimwise rebuilds the case without the document and its direct evidence references, recomputes the review and invalidates pack approval. Separate conversation text and provider records have their own lifecycles.
- `DELETE /api/thread/{id}` clears the thread's checkpoints, writes, blobs, uploads and in-memory webhook lookup. The browser removes its summary after success. Mock provider records, exported files, and tracing backends are separate stores.
- **Prototype limit.** Workspace routes use the thread ID in a guest session. The browser sends its own IDs for listing, and a pack checks document membership. Neither check establishes authenticated user ownership.

### Proposed production controls

**Specification (not run).** Authenticate each actor and derive access server-side from the tenant, patient and current case membership. Check that membership and the target resource on every read, file view, stream and mutation, including deletion. Check active representative scope separately from case membership, and verify the recipient before an external write. Use deletion events to track cleanup in all applicable stores and communicate external retention obligations. For the synthetic pilot, clear demo records at the end of each rehearsal and honor earlier deletion requests. Files and provider text are evidence inputs and cannot provide authority. [API implementation](../../backend/app/api/routes.py) · [Schemas](schemas.md) · [Rollout gates](../07-delivery/feasibility-and-rollout.md)

**Retention proposal, pending approval.** Keep the material needed while the case is open. Delete originals and working checkpoints by default 90 days after confirmed closure, or earlier on an authenticated owner request. Offer an export before scheduled deletion. Track active-store deletion separately from backup expiry and provider-held records. Set audit, backup and legally required retention before a real-data pilot. The guest prototype has no automatic retention schedule.

---

Previous: [Execution and memory](execution-and-memory.md) | [Index](../../README.md) | Next: [Mock provider connectors](provider-connectors.md)
