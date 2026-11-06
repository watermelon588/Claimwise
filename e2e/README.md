# Live end-to-end tests

`live_e2e.py` drives the real backend API the way the browser does: uploads, chat, buttons and approval cards. It runs against the connector gateway and the mock payer, hospital and bank, with real model calls and the configured checkpoint database. Mock operator calls play the insurer: they raise queries, decide, pay, generate PDF letters and inject faults. Every document is synthetic.

Results feed [docs/07-delivery/validation-plan.md](../docs/07-delivery/validation-plan.md) and [performance-report.md](../docs/07-delivery/performance-report.md) through `report.py`.

## Journeys

| Key | Journey |
|---|---|
| J1 | Standard claim: patient, connector, decision, verified payment |
| J2 | Caregiver: consent, versions, withdrawal, grievance, Ombudsman, revised decision |
| J3 | Household: two policies and a balance claim |
| J4 | Representative not registered at the payer |
| J5 | Insurer query through the connector |
| J6 | Lost response and payer outage |
| J7 | Manual route with mock letters and bank statement, malicious query letter |
| J8 | Cashless claim |
| J9 | Flawed documents, uploaded decision letter without clauses, prompt injection |
| J10 | Signed webhooks: forged, unknown, malformed |
| J11 | Security: input validation, forged buttons, cross-thread access, thread list |
| J12 | Concurrency on one thread |

Specs V-01 to V-37 are defined at the top of `live_e2e.py`.

## Run it

Four processes, each in its own terminal, from the repository root. `S` is any scratch folder outside the repository.

1. Mock services (port 8100), with their own database and documents folder so the run does not touch your demo data:
   `MOCK_DB_PATH=$S/mock.db DOCS_STORAGE_PATH=$S/documents mocks/.venv/Scripts/python.exe -m uvicorn mocks.main:app --app-dir mocks --port 8100`
2. Connector gateway (port 8101). It prints one-time codes and the server bearer key to its log:
   `CLAIMWISE_CONNECTOR_DEMO=1 mocks/.venv/Scripts/python.exe -m uvicorn connectors.app:app --port 8101 > $S/gateway.log`
3. Backend (port 8000), from `backend/`, with the key from the gateway log. Never paste the key into a file in the repository:
   `CONNECTOR_URL=http://127.0.0.1:8101 CONNECTOR_AGENT_KEY=<key> MOCK_WEBHOOK_SECRET=mock-secret-key-12345 TRACE_LOG=$S/trace.jsonl UPLOAD_DIR=$S/uploads uv run uvicorn app.main:app --port 8000`
   Model keys, `DATABASE_URL` and the optional `LANGSMITH_API_KEY` come from `backend/.env`.
4. The run (about 25 minutes, because every turn calls the real models):
   `PYTHONIOENCODING=utf-8 uv run --project backend python e2e/live_e2e.py --gateway-log $S/gateway.log --upload-dir $S/uploads`
   Use `--only J5,J6` to run some journeys, and `--out <file>` to choose the results file (default `e2e/results/latest.json`).

Then write the reports. Later result files replace whole journeys from earlier ones:

`python e2e/report.py --results e2e/results/latest.json [rerun.json] --trace $S/trace.jsonl --unit "50 passed"`

## Notes

- Threads are named `qa037-<journey>-<run>` and stay in the checkpoint database. Delete them if you need a clean database.
- The harness changes the mock clock and faults and resets them afterwards. Do not run it against mocks someone else is using.
- A crash inside one journey is recorded as a failed V-36 check, and the other journeys still run.
- `e2e/results/` holds run output. It contains synthetic data only.
