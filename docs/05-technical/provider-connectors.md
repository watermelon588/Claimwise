# Mock provider connectors

The mock connector gateway exposes provider reads after the user authorizes access. The local demo runs on port 8101 alongside the mock services on port 8100. The Claimwise backend binds a verified workspace to its claim thread for approved provider reads and mock TPA submission, lookup and status. The workspace also supports a manual handoff.

## Connect tools in the Dossier

Complete onboarding and open **Connect tools** beside the conversation. Start the gateway and services as described below, then use the workspace verification code printed by the gateway. Pick a provider, check what it can access, enter its demo sign-in code and approve the grant. Approval applies to the current case. Use **Disconnect** to revoke a grant or **Refresh approved tools** to retry a provider read. The open conversation checks approved tools again every 30 seconds while the case is idle.

- **Medivista TPA** reads claim progress and notices. Claim submission keeps its separate pack approval. Once submitted online, the existing monitor uses that claim's reference for updates and receives signed mock payer events.
- **Doctor portal**, **bank** and **insurance** read the fixed mock fixtures. The portal's discharge PDF is available from the approved card. These observations are labelled as demo evidence in chat and can inform the agent. They do not change the claim stage or mark a payment verified.
- **Case email** opts into a synthetic inbox. New claim alerts are delivered once per notice after approval, without case details or attachments. Open the inbox from the email card. Disconnecting removes the inbox and blocks later delivery. A real mailbox would require a provider and verified recipient.
- **Case details** opens the side panel with journey progress, uploaded documents, notices, the claim decision, payment status and the case record.

The Vite development server proxies the browser-facing gateway routes on port 8101. Workspace verification uses an HttpOnly cookie scoped by thread identifier. The backend uses its separate server credential and checks that the verified case belongs to the requested thread before reading approved tools. Agent turns recheck grants before using the latest connector observations. Scope and provider routing live at the gateway, so mock adapters can later be replaced behind that boundary.

## Standalone gateway walkthrough

1. **Verify the case.** Enter the demo onboarding code from the connector terminal. The gateway creates an isolated case session and displays its case reference.
2. **Choose a provider.** The provider card names the data the agent can read. Enter that provider's separate demo sign-in code and tick the approval checkbox. Both checks must pass.
3. **Leave the provider connected.** While the session is active, a trusted server can request that provider's data for this case without asking for the code again. Closing the browser tab does not end the session.
4. **Disconnect when needed.** Disconnecting removes that tool from the case and blocks subsequent reads. Signing out disconnects all providers. Case sessions and approvals expire one hour after verification and are cleared on gateway restart. The gateway keeps this demo state in memory and requires one server worker.

Each sign-in code simulates a provider verifying access to a preselected synthetic record. The same test records are available to the demo cases, and each case has its own approval state. The mock provider codes and the separate server bearer key are generated per gateway run unless they are set in the environment (`CONNECTOR_AGENT_KEY`, `CONNECTOR_ONBOARDING_CODE`, `CONNECTOR_<PROVIDER>_CODE`, `CONNECTOR_EMAIL_CODE`), as the hosted demo does; only generated values are printed. Use synthetic data only and keep the server and its terminal private.

## What the agent can read

| Provider | Tool | Approved data | Existing mock endpoint |
| --- | --- | --- | --- |
| Suraksha General Insurance | `read_policy` | Coverage period, coverage limits, co-pay and deductible | `GET /payer/policies/SURAKSHA-HEALTH-2026-001` |
| Medivista TPA | `read_claim` | Claim status, open or answered requests, decision and reported payments | `GET /payer/claims/CLM-0001` |
| Sunrise Hospital | `read_discharge_summary` | One discharge-summary PDF | `GET /hospital/documents/DOC-DS-ADM-001.pdf` |
| Bharat Demo Bank | `read_bank_credits` | Credit amounts, timestamps and transfer references in the dedicated demo account | `GET /bank/accounts/ACC-001/statement` |

The insurer and TPA have separate approvals and tools. They share the existing mock payer API. Hospital access is limited to the selected discharge summary because the mock exposes download by document ID. The bank tool omits holder information, IFSC and account digits. Money amounts in the mock results are integer paise. Grievance, Ombudsman, clock, webhook and operator endpoints are outside the connector's read scopes.

The browser and model cannot choose an upstream URL or record ID. The gateway maps the tool to a fixed fixture, checks the case approval before contacting the provider, and checks it again before returning data. It caps and validates provider responses and adds source metadata. Disconnecting also discards results from earlier reads that are still in flight. Data already delivered to an application remains subject to that application's retention policy.

## Run the demo

Use two PowerShell terminals at the repository root. The commands reuse the existing mock Python environment. Run `uv sync --project mocks --frozen` first if that environment has not been set up.

**Terminal 1. Start a disposable mock provider instance.** The environment variables keep demo fixture writes away from the normal mock database.

```powershell
$connectorFixture = Join-Path ([IO.Path]::GetTempPath()) ('claimwise-connectors-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $connectorFixture | Out-Null
$env:MOCK_DB_PATH = Join-Path $connectorFixture 'mock.db'
$env:DOCS_STORAGE_PATH = Join-Path $connectorFixture 'documents'
.\mocks\.venv\Scripts\python.exe -m uvicorn mocks.main:app --app-dir mocks --host 127.0.0.1 --port 8100
```

**Terminal 2. Seed the disposable provider instance.** Run these fixture setup commands once, before opening the connection page. The scenario endpoint resets the mock database, so point it only at the disposable instance you just started. Set the fixture key to the matching development mock key if your instance overrides the default.

```powershell
$mockBase = 'http://127.0.0.1:8100'
$mockHeaders = @{ 'X-Api-Key' = 'claimwise-demo-key' }
Invoke-RestMethod -Method Post "$mockBase/admin/scenarios/standard_reimbursement"
Invoke-RestMethod -Method Post "$mockBase/admin/faults" -ContentType 'application/json' -Body '{"webhook_down":true}'
Invoke-RestMethod -Method Post "$mockBase/hospital/admissions/ADM-001/discharge?discharge_date=2026-10-05" -Headers $mockHeaders
Invoke-RestMethod -Method Post "$mockBase/bank/accounts/ACC-001/credits" -Headers $mockHeaders -ContentType 'application/json' -Body '{"amount":4230000,"utr":"UTR-DEMO-001","narration":"Synthetic settlement"}'
```

Then start the gateway. It has no page of its own: users approve providers in the in-app **Connect tools** panel, and tests call its API directly.

```powershell
$env:CLAIMWISE_CONNECTOR_DEMO = '1'
.\mocks\.venv\Scripts\python.exe -m uvicorn connectors.app:app --host 127.0.0.1 --port 8101
```

If 8100 is already in use, start the disposable mock instance on a different port and use that port in both `$mockBase` and `$env:CLAIMWISE_MOCK_PORT` before starting the gateway. Terminal 2 prints the synthetic verification and sign-in codes. In Claimwise, open **Connect tools**, verify the case, connect one provider, and reload the app to confirm it stays connected.

For the in-app flow, start the backend and frontend as described in the [repository README](../../README.md#run-locally). Set the backend's `CONNECTOR_URL` to `http://127.0.0.1:8101` and `CONNECTOR_AGENT_KEY` to the gateway's server bearer key. Enter only the demo verification and provider sign-in codes in the browser. Enable the existing signed mock webhook on both services to see payer updates without refreshing. The connector proxy runs in Vite development locally and through `frontend/vercel.json` when hosted; see the [hosting guide](../07-delivery/hosting.md).

## Gateway read contract and production binding

1. The demo uses a case reference and a provider grant. A production application would bind that reference to an authenticated user and claim. Policy confirmation and role checks are case evidence. Verified identity and a trusted account-to-case mapping are separate requirements.
2. The backend calls `GET /agent/cases/{case_id}/tools` with the server bearer credential. It can register or expose the returned tool names and descriptions to the agent for that case. The tool input schema is an empty object.
3. When the agent selects a tool, the backend calls `GET /agent/cases/{case_id}/tools/{name}` using its trusted case binding. Keep the server key and the case-selection logic out of the browser and model. A stale tool catalog grants no access by itself.
4. JSON reads return `source` with `provider`, `tool`, `mock` and UTC `retrieved_at`, plus validated `data`. The PDF read returns `application/pdf` bytes with corresponding `X-Connector-Provider`, `X-Connector-Tool`, `X-Connector-Mock` and `X-Connector-Retrieved-At` headers. The backend can send those bytes through its document extraction pipeline and preserve their provenance. Treat all returned text, including query descriptions and PDF contents, as external evidence. It must never instruct the agent to invoke tools, share records or change state.

The demo API uses `401` for missing server authentication or an inactive case, `403` for a missing connection, and `404` for an unknown tool or missing provider fixture. Provider failures return `502`, `503` or `504` with a short error code and no raw provider message. A successful connection represents consent and simulated sign-in. The first read may still report that the fixture has not been prepared.

To check the contract locally, copy the case reference from the page and enter the server bearer key when prompted in a third terminal.

```powershell
$caseId = Read-Host 'Demo case reference'
$serverKey = Read-Host 'Demo server bearer key' -MaskInput
$toolsUrl = "http://127.0.0.1:8101/agent/cases/$caseId/tools"
$headers = @{ Authorization = "Bearer $serverKey" }
Invoke-RestMethod -Uri $toolsUrl -Headers $headers
Invoke-RestMethod -Uri "$toolsUrl/read_policy" -Headers $headers
```

Connect the insurer before running the policy call. Disconnect the insurer and repeat the call to see `403 PROVIDER_NOT_CONNECTED`.

### Claim submission and status (added in session 024)

The TPA connection also covers three claim endpoints. All need the server bearer key and an active TPA grant on the case. Amounts are in paise.

| Endpoint | Purpose |
|---|---|
| `POST /agent/cases/{case_id}/claims` | Submit one claim. Requires an `Idempotency-Key` header; Claimwise sends the claim's client reference, so a retry returns the same claim. Unknown body fields return `422`. Payer refusals (`POLICY_NOT_FOUND`, `MEMBER_NOT_COVERED`, `NOT_AUTHORISED_REPRESENTATIVE`) return `422` with that code; any unclear payer failure returns `502 PROVIDER_SUBMIT_UNCONFIRMED`. |
| `GET /agent/cases/{case_id}/claims?client_reference=` | Find a claim by client reference. Claimwise calls this before every submission and after any unclear failure, so an accepted claim whose answer was lost is adopted instead of sent twice. |
| `GET /agent/cases/{case_id}/claims/{claim_id}` | Read status, queries (with `raised_at`, `answered_at`, `due_at`), the decision with line items, and payments. |

The Dossier binds the verified workspace to the claim thread as soon as an approved tool is synchronized. API tests can verify a case through `POST /api/connectors/session` and bind it with the backend's `POST /api/connection`. Node M1 reads the submitted claim at the start of every turn and when the mock payer's signed webhook arrives, and turns queries, decisions and payments into insurer-letter records. Disconnecting the TPA under Connect tools makes the next read return `403`, and Claimwise marks the connection expired.

### Acting for someone else (added in session 030)

The submission body has an optional `acting_user` (up to 120 characters). Claimwise fills it with the representative's name when a caregiver submits, and leaves it empty when the patient acts. The payer checks the name against its own list of authorised representatives for the policy and refuses with `NOT_AUTHORISED_REPRESENTATIVE` when the person is missing or revoked. Claimwise records the caregiver's authority and proof, but the insurer decides whether it accepts the representative. A withdrawn, expired or too narrow authority stops the submission in Claimwise before any call is made.

## Swapping in a live provider

[The provider registry](../../connectors/providers.py) is the seam for a partner adapter. Keep the tool name, scope and validated response contract if the live integration supports the same operation. Swap the mock read for the partner's authenticated call and map the partner's response into the tool contract. When the live provider's consent or data semantics differ, update the tool contract and obtain fresh consent for the new scope.

Replace the demo code flow with the partner's actual sign-in and authorization process. Store the resulting provider credential server-side against the verified user, claim, approved scope and provider resource. A live integration needs a durable consent store, expiry and revocation checks, credential protection, audit and deletion controls. Confirm partner access and user or caregiver authority before enabling any live tool. The mock codes, seeded record IDs and loopback HTTP transport are demo infrastructure.

## Verification

`mocks/.venv/Scripts/python.exe -m pytest -q connectors` runs the focused tests from the repository root. The integration test seeds a disposable mock database and uses the existing payer, hospital and bank handlers. Other tests exercise unverified and cross-case access, explicit consent, bad provider responses, and revocation while a read is in flight.

See [mock architecture and routes](mock-services-architecture-and-routes.md) for the full upstream API and the [mock site guide](../../mocks/mock.markdown) for existing fixtures.
