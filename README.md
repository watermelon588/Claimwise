# Claimwise

Claimwise helps patients and authorized caregivers keep a health insurance claim together from document preparation through submission, insurer requests, decisions, and payment verification. The same case file supports corrections, multiple policies, and follow-up when a decision changes.

**Current status:** Working prototype for synthetic claims. The workspace can prepare and export an evidence pack. It can also submit and monitor a claim through an authorized mock payer connection. [Product brief](docs/01-product-brief.md) · [Release scope questions](docs/decisions.md#open-questions)

## Read the design

| Area | Start here |
| --- | --- |
| Product and evidence | [Product brief](docs/01-product-brief.md), [evidence register](docs/02-research/evidence-register.md), [personas](docs/02-research/personas-and-situations.md), [alternatives](docs/02-research/alternatives.md), [sources](docs/02-research/sources.md) |
| Technical reference | [Stack and appendix](docs/05-technical/README.md), [API and tools](docs/05-technical/api-tool-matrix.md), [schemas and payloads](docs/05-technical/schemas.md), [connector guide](docs/05-technical/provider-connectors.md) |
| Experience and delivery | [UX sketches](docs/06-experience/ux-sketches.md), [implementation plan](docs/07-delivery/implementation-plan.md), [feasibility and rollout](docs/07-delivery/feasibility-and-rollout.md) |
| Assignment and project terms | [Traceability](docs/traceability.md), [decisions](docs/decisions.md), [glossary](docs/glossary.md) |

The assignment index tracks the lifecycle and journey documentation, graph set, function catalogue, and validation evidence separately. Current editable diagrams include [product context](docs/diagrams/src/g1-product-context.excalidraw) and [agent execution](docs/diagrams/src/g3-agent-graph.excalidraw). The final submission PDF and recorded walkthrough follow review of the complete package.

## Run locally

Use Python 3.13 and [uv](https://docs.astral.sh/uv/) for the services, and Node.js 22 for the frontend. In three terminals from the repository root:

**Backend**

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Set `GOOGLE_API_KEY` in the backend environment for document reading. Text chat uses the configured Gemini or Groq key. Set `DATABASE_URL` to save checkpoints in Neon, or leave it empty for an in-memory demo.

**Mock providers**

```powershell
cd mocks
uv sync
uv run uvicorn mocks.main:app --host 127.0.0.1 --port 8100
```

**Frontend**

```powershell
cd frontend
npm ci
npm run dev
```

Open [Claimwise](http://localhost:5173/), [the case workspace](http://localhost:5173/app) or [Mock Console](http://localhost:5173/mocks). The dev server routes the API and mock calls to the two Python services. See the [synthetic fixture guide](mocks/mock_documents/README.md) and the optional [connector setup](docs/05-technical/provider-connectors.md) for connected mock submission.

## Deployment and data

The [deployment guide](frontend/DEPLOYMENT.md) covers a manual Vercel frontend preview and separate Python service hosting. Use synthetic records. The prototype's guest workspace and mock admin routes require additional access controls before handling real claim data. [Data handling and permissions](docs/05-technical/actions-permissions-and-data.md)
