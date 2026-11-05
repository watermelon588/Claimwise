# Mock provider connectors

The mock connector gateway exposes provider reads after the user authorizes access. The local demo runs on port 8101 alongside the mock services on port 8100. The Claimwise backend can bind the demo case to a thread for mock TPA submission, lookup and status. Other reads are available at the gateway. The workspace also supports a manual handoff.

## What a user sees

1. **Verify the case.** Enter the demo onboarding code from the connector terminal. The gateway creates an isolated case session and displays its case reference.
2. **Choose a provider.** The provider card names the data the agent can read. Enter that provider's separate demo sign-in code and tick the approval checkbox. Both checks must pass.
3. **Leave the provider connected.** While the session is active, a trusted server can request that provider's data for this case without asking for the code again. Closing the browser tab does not end the session.
4. **Disconnect when needed.** Disconnecting removes that tool from the case and blocks subsequent reads. Signing out disconnects all providers. Case sessions and approvals expire one hour after verification and are cleared on gateway restart. The gateway keeps this demo state in memory and requires one server worker.

Each sign-in code simulates a provider verifying access to a preselected synthetic record. The same test records are available to the demo cases, and each case has its own approval state. The mock provider codes and the separate server bearer key are generated per gateway run. Use synthetic data only and keep the loopback server and its terminal private.

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

Then start the gateway and open [the local connection page](http://127.0.0.1:8101/).

```powershell
$env:CLAIMWISE_CONNECTOR_DEMO = '1'
.\mocks\.venv\Scripts\python.exe -m uvicorn connectors.app:app --host 127.0.0.1 --port 8101
```

If 8100 is already in use, start the disposable mock instance on a different port and use that port in both `$mockBase` and `$env:CLAIMWISE_MOCK_PORT` before starting the gateway. Terminal 2 prints the synthetic verification and sign-in codes. Verify a case, connect one provider, and refresh the page to confirm it stays connected.

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

In the Claimwise backend, the user binds a case to a claim thread by pasting the case reference shown on this page (mock only; no real login). The backend keeps the case reference on the server. Node M1 reads the submitted claim at the start of every turn and when the mock payer's signed webhook arrives, and turns queries, decisions and payments into insurer-letter records. Revoking the TPA connection here makes the next read return `403`, and Claimwise marks the connection expired.

### Acting for someone else (added in session 030)

The submission body has an optional `acting_user` (up to 120 characters). Claimwise fills it with the representative's name when a caregiver submits, and leaves it empty when the patient acts. The payer checks the name against its own list of authorised representatives for the policy and refuses with `NOT_AUTHORISED_REPRESENTATIVE` when the person is missing or revoked. Claimwise records the caregiver's authority and proof, but the insurer decides whether it accepts the representative. A withdrawn, expired or too narrow authority stops the submission in Claimwise before any call is made.

## Swapping in a live provider

[The provider registry](../../connectors/providers.py) is the seam for a partner adapter. Keep the tool name, scope and validated response contract if the live integration supports the same operation. Swap the mock read for the partner's authenticated call and map the partner's response into the tool contract. When the live provider's consent or data semantics differ, update the tool contract and obtain fresh consent for the new scope.

Replace the demo code flow with the partner's actual sign-in and authorization process. Store the resulting provider credential server-side against the verified user, claim, approved scope and provider resource. A live integration needs a durable consent store, expiry and revocation checks, credential protection, audit and deletion controls. Confirm partner access and user or caregiver authority before enabling any live tool. The mock codes, seeded record IDs and loopback HTTP transport are demo infrastructure.

## Verification

`mocks/.venv/Scripts/python.exe -m pytest -q connectors` runs the focused tests from the repository root. The integration test seeds a disposable mock database and uses the existing payer, hospital and bank handlers. Other tests exercise unverified and cross-case access, explicit consent, bad provider responses, and revocation while a read is in flight.

See [mock architecture and routes](mock-services-architecture-and-routes.md) for the full upstream API and the [mock site guide](../../mocks/mock.markdown) for existing fixtures.
