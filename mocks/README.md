# Claimwise Mock Services

Mock external systems for Claimwise demo and integration testing:
- M1 Payer service (Insurer + TPA)
- M2 Hospital service (Billing & Cashless desk)
- M3 Bank service (Account credits & statements)
- M4 Grievance & Ombudsman service (GRO, Bima Bharosa, Ombudsman)
- M5 Operator console (Web dashboard, scenarios, clock control)
- M6 Synthetic document generator (PDF generation for test journeys)

## Quick Start

```bash
cd mocks
uv sync
uv run uvicorn mocks.main:app --port 8100 --reload
```

Interactive OpenAPI docs will be available at: http://localhost:8100/docs
Console UI: http://localhost:8100/
