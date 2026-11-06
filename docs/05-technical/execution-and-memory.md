# Execution and memory

**Status:** Draft runtime reference. See [the graph source](../../backend/app/agent/graph.py) for ordering and [state types](../../backend/app/agent/state.py) for exact reducers.

| Concern | Current prototype | Design boundary |
| --- | --- | --- |
| Turn execution | HTTP turn or SSE stream runs a LangGraph thread. Deterministic routes handle explicit buttons. Policy confirmation and pack approval use an interrupt and later resume. | This is a request-driven workflow. An interrupted human approval releases the active request. |
| Concurrency | The API uses process-local thread locks around graph invocations and streams. | Multi-worker or multi-instance serialization is outside the prototype. Use one instance for the demo. |
| Persistence | Configured Neon/Postgres stores checkpoints. In-memory fallback loses checkpoints on restart. Original upload bytes are local files separate from checkpoints. | Restart recovery requires both a persistent checkpointer and access to the original file storage. |
| Waiting | Update checks happen on turns, thread refresh/polling while the app is open, and signed mock webhook notifications. | Long waits do not occupy a worker. A durable scheduler and delivery retries across deployments are future work. |
| Recompute | New evidence is checked against existing state. Exact duplicate uploads are refused, revised documents can supersede prior versions, and content changes invalidate stale approvals. | Earlier claim rounds and archived evidence remain visible. A revised decision can reopen payment checks without restarting onboarding. |
| Ambiguous provider write | The submission carries a stable client reference and an idempotency key. Claimwise checks for a receipt before replaying a request that may have succeeded. | Recover the external outcome before asking the user to try again. Reconcile manual submissions with user-supplied receipt or reference. |
| Notices and sync | Notifications and imported records have stable identifiers. The process holds an in-memory claim-to-thread map for webhook routing. | Reopening the thread rebuilds the map and refreshes the provider snapshot. Prior reminder entries can remain visible. |

The backend connector HTTP call has a 10-second timeout and a 1 MiB response read cap. The gateway uses a separate 5-second upstream timeout. Model request limits and retry behavior depend on SDK and provider configuration. [Backend connector](../../backend/app/connector.py) · [Gateway](../../connectors/app.py) · [Checkpointer](../../backend/app/db.py) · [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

---

Previous: [Models and retrieval](models-and-retrieval.md) | [Index](../../README.md) | Next: [Actions, permissions and data](actions-permissions-and-data.md)
