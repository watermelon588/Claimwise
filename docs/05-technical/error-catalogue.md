# Error catalogue

**Status:** Draft prototype reference. Exact responses are defined by [Claimwise API routes](../../backend/app/api/routes.py), the [connector guide](provider-connectors.md) and the [mock route reference](mock-services-architecture-and-routes.md).

| Signal | Meaning | User or operator recovery |
| --- | --- | --- |
| 400 on link | Case id is invalid, expired, or missing the TPA grant. | Verify the case again under Connect tools and approve Medivista TPA. |
| 401 on webhook | Signature verification failed. | Verify the shared secret and signing of the raw request body. Inspect the sender before retrying. |
| 404 on an original or connector read | Original unavailable in the current pack, or gateway tool/fixture is missing. | Check the ready pack and correct source document or mock case. |
| 409 on upload | Same bytes already stored for the thread. | Use the earlier copy or upload a corrected file with different bytes. |
| 409 on action, resume, authority, or pack | An action is stale, a card is pending, no authority is active, or evidence is incomplete. | Refresh the thread and follow the current card or blocker. |
| 413 or 415 | File exceeds the configured limit, or its type/signature is unsupported. | Provide a supported PDF, PNG or JPEG within the limit. |
| 422 | Request schema, thread ID, proof, action, or event is invalid. | Correct the field or use the action offered in the workspace. |
| 500 / 503 | Graph or checkpoint error, model credentials missing, or gateway unavailable. | Check health and service configuration, then load the latest state before retrying. |
| SSE error frame | The streamed turn failed after the connection opened. | Read the current thread before resending. The HTTP status alone does not establish success. |
| Mock refusal, revoked grant or unconfirmed write | Payer refused, authorization expired, or the response was lost. | Resolve the refusal or reconnect. For an unconfirmed write, reconcile by client reference before retrying. |

A non-claim upload can also be rejected during document classification and returned in a successful turn envelope. It is distinct from transport validation errors. [Document parsing](../../backend/app/agent/onboarding.py)

---

Previous: [Schemas and example payloads](schemas.md) | [Index](../../README.md) | Next: [Models and retrieval](models-and-retrieval.md)
