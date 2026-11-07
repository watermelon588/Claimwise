# API and tool matrix

**Status:** Draft reference for the prototype and external access evidence.

## Prototype operation fields

Shared fields apply to every operation in the corresponding group. The Claimwise and gateway API paths below are implemented **prototype** contracts. The proposed authenticated design is in [permissions and data](actions-permissions-and-data.md). The local evidence column points to past checks; other cases are **Specification (not run)**.

**Claimwise API.** Docs: [OpenAPI route definitions](../../backend/app/api/routes.py) and [Pydantic schemas](../../backend/app/schemas.py). Except for health (public) and webhook (HMAC), auth is possession of the guest thread ID. Scope is the supplied thread and any matching resource within it. No API fee, per-user request quota or cursor. `GET /threads` accepts up to 25 supplied valid IDs, and upload defaults to 10 MB. Authenticated ownership and production load have not been tested.

| Method and path | Input and result | Approval or prerequisite | Synthetic evidence / fallback |
|---|---|---|---|
| `GET /api/health` | None → HealthResponse | None | API smoke; inspect database status separately. |
| `POST /api/chat` | ChatRequest → ChatResponse | Current thread; answer cards through the resume route | V-06; inspect saved state before resending. |
| `POST /api/chat/stream` | ChatRequest → SSE activity/token/done/error | Same guest scope as chat | Stream tests; hydrate saved thread if interrupted. |
| `POST /api/documents` | Multipart thread ID/file → ChatResponse and processed ID | Allowlisted MIME, magic bytes and size | V-01/04/18/28; retry incomplete file or provide a replacement. |
| `POST /api/thread/{thread_id}/documents/{document_id}/retry` | Path IDs → ChatResponse and processed ID | Retained failed or incomplete original | API regression; re-upload same bytes if missing. |
| `POST /api/resume` | ResumeRequest → ChatResponse | Pending card; validate policy corrections | V-02/07; keep card pending after invalid corrections. |
| `GET /api/threads` | Comma-separated `ids` → summary array | Caller already holds IDs | V-35 and API regression; retry failed batch, preserve local summaries. |
| `GET /api/thread/{thread_id}` | Path ID → ChatResponse with history | No separate approval; pending run returns saved state | V-34 and API regression; retry hydration on 500. |
| `DELETE /api/thread/{thread_id}/documents/{document_id}` | Path IDs → sanitized ChatResponse | Dossier confirmation; API checks IDs | API regression; repeat after partial file-cleanup failure. |
| `DELETE /api/thread/{thread_id}` | Path ID → 204 | Dossier confirmation; API checks ID | API regression; repeat cleanup on 500. |
| `POST /api/action` | ActionRequest → ChatResponse | Offered action and matching form data; separate human card for consequential actions | V-07/29; refresh current actions after stale choice. |
| `POST /api/connection` | ConnectionRequest → ChatResponse | Valid gateway case with active TPA grant | V-09; verify case or use manual export. |
| `POST /api/connection/sync` | ConnectionRequest → ChatResponse | Verified same-thread workspace, complete onboarding and no pending run | API regression; reconnect or use supplied evidence. |
| `POST /api/connection/remove` | ThreadRequest → ChatResponse | No pending card for state edit | Local unlink; revoke separately in Connect tools. Dedicated live check not recorded. |
| `POST /api/claim-type` | ClaimTypeRequest → ChatResponse | User choice; route change blocked after submission | V-37; continue with existing submitted route. |
| `POST /api/authority` | AuthorityRequest → ChatResponse | User supplies role, scope, proof and dates; validate against evidence | V-19; correct proof or have patient act. |
| `POST /api/authority/withdraw` | ThreadRequest → ChatResponse | Active authority | V-20; re-record valid authority before a delegated action. |
| `POST /api/notifications/read` | ThreadRequest → ChatResponse | No pending card if a write is needed | Dedicated live check not recorded; notices still visible. |
| `GET /api/pack/{thread_id}` | Path ID → pack JSON | Ready pack, no separate download approval | J1 pack review; return to checklist if not ready. |
| `GET /api/pack/{thread_id}/pdf` | Path ID → PDF | Ready pack | V-08; retain ready pack and retry download. |
| `GET /api/pack/{thread_id}/eml` | Path ID → MIME email draft | Ready pack; user reviews recipient before sending | V-08; use manual email handoff. |
| `GET /api/pack/{thread_id}/documents/{document_id}` | Path IDs → original bytes | Ready pack and document membership | V-30; go to the correct case/pack. |
| `POST /api/webhooks/mock` | Signed raw event → 202 JSON acknowledgement | HMAC-SHA256 with configured shared secret; matched claim only | V-11; next thread refresh reconciles missed events. |

**Connector gateway.** Docs: [routes and request types](../../connectors/app.py), [provider adapters and schemas](../../connectors/providers.py) and [mock connector guide](provider-connectors.md). No operation fee or cursor. The demo allows 64 active verification sessions and expires them after one hour. The inbox keeps up to 100 entries. Browser auth means the HttpOnly case cookie with matching workspace binding. Agent auth means the server bearer and active case; grants apply to the named provider. Local tests use synthetic records. Live partner access, provider limits and real mail are untested.

| Method and path | Input and result | Auth, scope and approval | Synthetic evidence / fallback |
|---|---|---|---|
| `POST /api/connectors/session` | Verification code and workspace header → 201 case ID/cookie | Demo onboarding code; no provider grant yet | Connector verification tests; verify again on expiry. |
| `GET /api/connectors` | None → provider descriptors and connected flags | Browser case cookie | Connector consent tests; verify again if missing. |
| `DELETE /api/connectors/session` | None → 204, clears cookie and grants | Browser case cookie | Connector isolation tests; start a fresh case for access. |
| `POST /api/connectors/{provider}` | Consent code and boolean → connected flag | Browser case cookie, matching provider code and affirmative approval | Connector consent tests; manual handoff without grant. |
| `DELETE /api/connectors/{provider}` | Provider name → 204 | Browser case cookie, named provider only | Revocation tests; rely on supplied records. |
| `GET /api/connectors/inbox` | None → demo notice rows | Browser case cookie, email grant | Demo mail tests; use in-app notices. |
| `GET /api/connectors/document` | None → synthetic PDF | Browser case cookie, hospital grant | Local fixture adapter tested; provide a copy on failure. |
| `GET /agent/cases/{case_id}/tools` | Case ID and workspace header → approved descriptors | Agent bearer and matching workspace; no upstream read | Connector isolation tests; refresh grants. |
| `GET /agent/cases/{case_id}/tools/{name}` | Case/tool IDs; no query fields → sourced JSON or PDF | Agent bearer and matching provider grant | Fixture and revocation tests; use supplied evidence. |
| `POST /agent/cases/{case_id}/mail` | MailBatch → delivery acknowledgement | Agent bearer, email grant, post-consent notices only | Demo mail tests; deduplicate by notice ID and retain in-app notices. |
| `POST /agent/cases/{case_id}/claims` | ClaimSubmission and Idempotency-Key → 201 sourced claim | Agent bearer, active TPA grant; Claimwise checks pack approval and delegated scope | V-09/10/21; lookup before retry. |
| `GET /agent/cases/{case_id}/claims?client_reference=` | Reference → sourced matching claims | Agent bearer and TPA grant | V-10; keep outcome unconfirmed until a read succeeds. |
| `GET /agent/cases/{case_id}/claims/{claim_id}` | Claim ID → sourced status, queries, decision and payments | Agent bearer and TPA grant | V-11; ask for payer evidence if unavailable. |
| `POST /agent/cases/{case_id}/claims/{claim_id}/documents` | QueryAnswer → sourced answer | Agent bearer and TPA grant; approve exact reply list in Claimwise | V-13 partially passed; confirm status before retry or use human handoff. |

| Fixed tool on the gateway tool path | Scope | Request and response / fallback |
|---|---|---|
| `read_policy` | `policy.read` | No arguments. Synthetic policy coverage, limits and cost sharing; use supplied policy. |
| `read_claim` | `claim.read claim.submit` | No arguments. Synthetic TPA claim, queries, decision and reported payments; use payer receipt or letter. |
| `read_discharge_summary` | `discharge_summary.read` | No arguments. Discharge PDF with provenance headers; provide an upload. |
| `read_bank_credits` | `credits.read` | No arguments. Credit amount/date/reference only; use supplied statement. |

**Model calls.** No pagination. Synthetic provider access was measured in the [performance report](../07-delivery/performance-report.md); real-user data handling and production throughput remain untested. Requests are server-side after a demo user starts a turn or uploads. Models cannot authorize a claim write. Dated rates and worked costs are in the [cost model](../07-delivery/feasibility-and-rollout.md).

| Provider method and path | Auth and scope | Schemas and purpose | Quota, cost and fallback |
|---|---|---|---|
| Gemini `POST /v1beta/models/{model}:generateContent` and `POST /v1beta/models/{model}:streamGenerateContent` | Server API key; model access under the configured project | `GenerateContentRequest` and response/chunks. O1 PDF/image extraction → DocumentExtraction; I1 text → Intent; A1 text/tool messages → reply/tool calls. [Google reference](https://ai.google.dev/api/generate-content) | Account/project limits. Historical test reached 429; current limits come from AI Studio. Standard paid rate $0.25/$1.50 per million input/output tokens for non-audio. Spare Gemini key, then Groq for text; retry or replace document for extraction. |
| Groq `POST /openai/v1/chat/completions` | Server bearer API key; configured organization and model | Chat completion messages, tool schemas, structured intent or streamed/text reply. [Groq reference](https://console.groq.com/docs/api-reference) | Organization rate limits by account and model. Standard $0.075/$0.30 per million uncached input/output tokens. Use Gemini text when available; extraction has no Groq path. [Groq limits](https://console.groq.com/docs/rate-limits) |

For live insurer, TPA, hospital, bank, NHCX and grievance portals, Claimwise has no verified integration operation to exercise. Method/path, partner credentials, schemas, paging, quotas, charges and approval terms are **unverified or not applicable to the manual channel**. The rows below identify public documentation and human fallbacks.

### In-process agent tools

The following tools have no HTTP method, API path, independent credentials, pagination, quota or fee. They run under the current thread's graph scope. Inputs and return types are in [agent tools](../../backend/app/agent/tools.py), with model request charges in the [cost model](../07-delivery/feasibility-and-rollout.md). The historical performance trace observed all four tools. Cross-tenant use and production load are untested.

| Tool operation | Input and output | Approval and fallback |
|---|---|---|
| `claim_deadline` | Supported event and ISO date → list of dated rules | Read-only. Ask for a valid event and date when input is missing. |
| `record_role` | Role, patient name, relation → state update and ToolMessage | User supplies facts. Missing coverage or authority remains an onboarding blocker. |
| `update_claim` | Optional claim type, date and reference → merged facts and ToolMessage | User supplies facts. Use the dedicated claim type control for a structured route selection. |
| `prepare_submission` | Injected case state and tool call ID → blockers or pack approval pause | Explicit human approval binds the hash. Correct blockers or use the manual handoff after approval. |

## Live services and manual handoffs

| Provider | Auth, approval and access evidence | Contract, limits and fallback |
|---|---|---|
| Live insurer and TPA | Partner access and claimant permissions unverified. Published claimant portals show a manual route. [S-08](../02-research/sources.md) | Provider scopes, quotas, cost, schemas and access require agreement. Manual submission and receipt tracking. |
| NHCX | Documented FHIR profiles. [S-07](../02-research/sources.md) Claimwise partner onboarding and credentials unverified. | Profile documentation describes messages, with access and production limits pending. Manual hospital or payer handoff. |
| Live hospital and bank | Claimwise has no verified live access. | Obtain documents or statements from the user or authorized organization. |
| Bima Bharosa and Insurance Ombudsman | Official public filing procedures. [S-06 and S-29](../02-research/sources.md) Prototype does not send to either. | Human reviews eligibility, files on the official channel and returns the acknowledgement. |

Local evidence: [validation report](../07-delivery/validation-plan.md) · [API regression tests](../../backend/tests/test_api.py) · [connector tests](../../connectors/test_connectors.py) · [mock operator routes](mock-services-architecture-and-routes.md)

---

Previous: [Function catalogue](function-catalogue.md) | [Index](../../README.md) | Next: [Schemas and example payloads](schemas.md)
