# API and tool matrix

**Status:** Draft. Internal routes below are implemented for the prototype. External access labels describe Claimwise's evidence, rather than an estimate of all APIs available in the market.

## Claimwise API

Root prefix is /api. The backend's /docs route exposes generated OpenAPI when the service is running. [API routes](../../backend/app/api/routes.py) · [Request and response types](schemas.md)

| Operation | Input and result | Gate or recovery |
| --- | --- | --- |
| GET /health | Service status, database mode/health and configured model provider. | Check the database field separately. |
| POST /chat; POST /chat/stream | Thread ID and message. Returns a turn envelope or server-sent events. | Continue on the same thread. On an interrupted stream, inspect current state before resending. |
| POST /documents; POST /resume | Multipart thread and file, or a pending card answer. Returns updated turn. | Validate file type, size, fingerprint and thread ID. Resume only a pending card. |
| GET /threads; GET /thread/{thread_id} | Recent session summaries, or the thread envelope with history and saved answers. | Demo only. History listing is capped and has no cursor. |
| POST /action | Thread ID, offered action and optional fields. Returns updated turn. | Backend rechecks whether the action is offered. Browser-only upload or download actions use their own routes. |
| POST /connection; POST /connection/remove | Thread ID and demo case code for linking, thread ID only to unlink. | Link verifies the mock gateway case and TPA connection. User can use manual handoff. |
| POST /authority; POST /authority/withdraw | Thread ID and representative, scope and proof fields, or thread ID to withdraw. | Checks role, proof and dates. The mock payer separately checks the representative. |
| POST /notifications/read | Thread ID. Returns refreshed notifications. | Updates this thread's read state. |
| GET /pack/{thread_id}; GET /pack/{thread_id}/pdf; GET /pack/{thread_id}/eml; GET /pack/{thread_id}/documents/{document_id} | Pack review JSON, PDF, email draft, or an included original. | Requires a ready pack. Download is distinct from approval and submission. |
| POST /webhooks/mock | Raw signed mock event body. Returns a 202 acknowledgement. | Requires configured HMAC secret. Connector status is read separately to confirm payer state. |

Main browser endpoints use a prototype thread ID without account authentication. The local service defines a configurable upload cap of 10 MB by default. Application-level per-user quotas and paging beyond the recent-thread listing are unspecified. [Configuration](../../backend/app/config.py) · [Data boundaries](actions-permissions-and-data.md)

## Provider, gateway and model operations

| Provider and operation | Auth, approval and access evidence | Contract, limits and fallback |
| --- | --- | --- |
| Mock gateway policy, TPA claim, hospital PDF, bank credit reads | Server bearer credential, active case and relevant provider grant. Verified with local synthetic records. | Validated JSON or PDF with provenance. Gateway handles upstream failures. Fall back to supplied evidence. |
| Mock gateway TPA submit, lookup by client reference and read by claim ID | Active TPA grant and server credential. Submit requires the current approved pack and valid caregiver scope where applicable. Tested against the local mock payer. | Write carries Idempotency-Key. Look up before retrying uncertain outcomes. If no eligible connection, export a pack for manual handling. |
| Gemini document extraction and structured/chat calls | Server API key. Gemini is the document reader. Prototype evidence is synthetic. | Pydantic extraction schema. Account quotas and billing are provider-specific. Ask for manual facts if the document cannot be read. |
| Groq text and structured calls | Server API key; configurable primary/fallback for text. | Text model and tools, no configured document reader. Quota and cost depend on model and account. |
| Live insurer and TPA | Partner access and claimant permissions unverified. Published claimant portals show a manual route. | Provider scopes, quotas, cost, schemas and access require agreement. Manual submission and receipt tracking. |
| NHCX | Documented FHIR profiles. Claimwise partner onboarding and credentials unverified. | Profile documentation describes messages, with access and production limits pending. Manual hospital or payer handoff. |
| Live hospital and bank | Claimwise has no verified live access. | Obtain documents or statements from the user or authorized organization. |
| Bima Bharosa and Insurance Ombudsman | Official public filing procedures. Prototype does not send to either. | Human reviews eligibility, files on the official channel and returns the acknowledgement. |

Mock operations use a bounded synthetic dataset without commercial quotas or provider charges. Full schemas, methods, paths, headers and errors are in the [connector guide](provider-connectors.md) and [mock routes](mock-services-architecture-and-routes.md). Vendor references and costs are indexed in the [rollout plan](../07-delivery/feasibility-and-rollout.md). Access evidence: [S-06, S-07, S-08, S-29](../02-research/sources.md).

---

Previous: [Technical reference](README.md) | [Index](../../README.md) | Next: [Schemas and examples](schemas.md)
