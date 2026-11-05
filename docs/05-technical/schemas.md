# Schemas and example payloads

**Status:** Draft reference. [Pydantic HTTP models](../../backend/app/schemas.py), [extraction models](../../backend/app/agent/onboarding.py), and [checkpoint types](../../backend/app/agent/state.py) define the current fields.

## Public API shapes

| Shape | Fields and constraints |
| --- | --- |
| Thread identifier | 1 to 100 letters, digits, underscores or hyphens. Identifies a demo checkpoint and upload directory. |
| Chat request | thread_id and message. Message length is 1 to 8,000 characters. |
| Upload | Multipart thread_id and one file. PDF, PNG or JPEG, with signature checked. Default size cap is 10 MB. |
| Resume | thread_id, approved, and optional corrections. Policy changes are limited to the editable extraction fields and revalidated. |
| Action | thread_id, action, and optional data with up to five string-valued fields. Action IDs use lowercase letters and underscores. |
| Authority | thread_id, representative_name, basis, optional proof_doc_id, scope, and optional expires_on. Proof is a 32-character hex document ID. |
| Turn envelope | thread_id, reply, pending, onboarding, claim, documents, actions, notifications, submission, connection, history, answers, authority, audit, household, dispute. Individual fields can be null or empty. |

Stream data frames use type activity, token, done or error. A done frame includes the turn envelope. The response projection removes file paths, connector case IDs and submission client references. [Response shaping](../../backend/app/api/routes.py)

## Domain records

| Record | Key and provenance | Important values |
| --- | --- | --- |
| Document | Server ID for uploads, stable provider-derived ID for connector records. | Status, type, facts, source, version linkage, and upload SHA-256 where applicable. |
| Policy | Source doc_id. | Insurer, TPA, policy number, type, members, sum insured, cover dates, confirmation status, corrected fields. |
| Claim and round | ClaimInfo, selected policy doc ID and round under a thread. | Patient role, route, claim number, submitted date, archived earlier rounds and balance evidence. |
| Submission approval and result | Exact pack hash for approval; client reference for a connector attempt. | Route, timestamp, submitted/refused/unconfirmed status, payer claim ID when known. |
| Authority and audit | Representative, proof document reference, scope, expiry, audit entry IDs. | Active/withdrawn record and derived validity; proof and insurer acceptance are separate. |
| Decision, query and payment | Extracted from insurer letters, statements or normalized mock snapshots. | Stated outcome and clause, original requested label, amounts, transaction reference and coverage period. |
| Dispute and notifications | Decision document ID, filing references, stable notice IDs. | Approved draft hash, user-recorded filing dates, and read state. |

Dates in extraction examples use YYYY-MM-DD and event timestamps use ISO format. The Claimwise domain uses whole rupees. Mock provider amounts use integer paise, including the approved connector submission payload. [Mock currency rules](mock-services-architecture-and-routes.md#21-currency-and-amounts) · [Submission mapping](../../backend/app/agent/submission.py)

## Synthetic examples

- [Chat request](payloads/chat-request.json)
- [Pending policy confirmation response](payloads/policy-pending-response.json), shown after the policy is read.
- [Policy correction](payloads/policy-resume-request.json)
- [Mock connector submission body](payloads/mock-submit-request.json). The gateway also requires an active TPA grant, a server bearer credential and an Idempotency-Key header. The sample includes only the body.

---

Previous: [API and tool matrix](api-tool-matrix.md) | [Index](../../README.md) | Next: [Error catalogue](error-catalogue.md)
