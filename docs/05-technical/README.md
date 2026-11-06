# Technical reference

**Status:** Draft reference for the current local prototype. Use the linked implementation as the source of truth for exact field and route behavior.

## Stack and rationale

| Area | Implementation | Why it fits |
| --- | --- | --- |
| Workspace | React, Vite and Tailwind | One browser workspace for structured forms, document review and streamed chat. [Frontend manifest](../../frontend/package.json) |
| API and validation | FastAPI and Pydantic | Explicit request boundaries, generated OpenAPI and typed extraction and response envelopes. [Routes](../../backend/app/api/routes.py) · [Schemas](../../backend/app/schemas.py) |
| Orchestration | LangGraph | Reuses graph execution, interrupts and checkpointing for approval and resume. Claimwise supplies the domain rules. [Graph](../../backend/app/agent/graph.py) · [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) |
| Persistence | Neon Postgres or in-memory checkpointer; local upload files | Saves graph state independently of the browser. Local storage keeps the demo simple. [Database setup](../../backend/app/db.py) |
| Model access | Gemini for documents; configurable Gemini/Groq for text | Document input and structured output are useful for extraction. Evidence checks and consequential actions stay in code. [Models and retrieval](models-and-retrieval.md) |
| Mock providers | Separate FastAPI app, SQLite, generated PDFs, connector gateway | Reproducible scenarios and isolated provider state for development. [Mock routes](mock-services-architecture-and-routes.md) · [Connector guide](provider-connectors.md) |

## Appendix index

- [API and tool matrix](api-tool-matrix.md), [schemas and sample payloads](schemas.md), and [error catalogue](error-catalogue.md)
- [Models and retrieval](models-and-retrieval.md), [execution and memory](execution-and-memory.md), and [actions, permissions and data](actions-permissions-and-data.md)
- [Original external-system build brief](external-systems-and-mocks.md), [mock route reference](mock-services-architecture-and-routes.md), and [synthetic document fixtures](../../mocks/mock_documents/README.md). Use the current API and tool matrix above for access status.
- [Milestones](../07-delivery/implementation-plan.md) and [cost and measurement plan](../07-delivery/feasibility-and-rollout.md)

The detailed function catalogue and state/transition diagrams are tracked separately in the [assignment index](../traceability.md).

---

Previous: [Research sources](../02-research/sources.md) | [Index](../../README.md) | Next: [API and tool matrix](api-tool-matrix.md)
