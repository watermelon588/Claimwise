# Claimwise

Claimwise is an AI agent that helps patients and authorized caregivers manage health insurance claims, from preparation and evidence collection through submission, insurer questions, decisions, disputes and payment verification. It keeps responsibilities and next steps clear across hospitals, insurers and family members.

> Status: research and design stage, with an early backend and frontend scaffold under development. Scope and jurisdiction are not final; open points are marked TBD in the documents and tracked in [docs/decisions.md](docs/decisions.md).

## How to read this repository

Read the documents in the order below. Each page ends with Previous / Index / Next links. Requirements from the assignment brief are mapped to the files that satisfy them in [docs/traceability.md](docs/traceability.md).

| # | Section | Document | Status |
|---|---|---|---|
| 1 | Product brief | docs/01-product-brief.md | Planned |
| 2 | Research | [Evidence register](docs/02-research/evidence-register.md) | Draft |
| 2 | Research | [Alternatives](docs/02-research/alternatives.md) | Draft |
| 2 | Research | [Personas and situations](docs/02-research/personas-and-situations.md) | Draft |
| 2 | Research | [Sources](docs/02-research/sources.md) | Draft |
| 3 | Lifecycle | docs/03-lifecycle/lifecycle-map.md, branch-matrix.md | Planned |
| 4 | Architecture | docs/04-architecture/ (five graphs) | Planned |
| 5 | Technical sheet | docs/05-technical/ | Planned |
| 6 | Experience | docs/06-experience/ (UX sketches, journeys) | Planned |
| 7 | Delivery | docs/07-delivery/ (validation, implementation plan, rollout) | Planned |

Reference pages: [traceability](docs/traceability.md), [decisions and assumptions](docs/decisions.md), [glossary](docs/glossary.md).

Status labels: **Planned** (not written), **Draft** (written, not yet reviewed), **Reviewed** (approved by the project owner), **Final** (included in the submission PDF).

## Submission package

| Item | Location | Status |
|---|---|---|
| Design documents | this repository, docs/ | In progress |
| Editable diagram sources | docs/diagrams/src/ | Draft: G1 product context, G3 agent graph v0.2 |
| Consolidated PDF | submission/claimwise-design.pdf | Planned, generated last |
| Walkthrough video | video/walkthrough-script.md plus hosted link | Planned |
| Working prototype | linked here as one unit once built | Planned |

## Development

Stack: FastAPI + LangGraph (backend), React + Vite + Tailwind CSS (frontend), Neon Postgres for agent checkpoints, Gemini 3.1 Flash Lite as the LLM with Groq GPT-OSS 20B as automatic fallback.

```
backend/    FastAPI app (app/main.py), agent graph (app/agent/), settings (app/config.py), DB (app/db.py)
frontend/   React app (src/App.jsx); /api is proxied to the backend in development
```

Backend (needs [uv](https://docs.astral.sh/uv/)):

```
cd backend
cp .env.example .env      # add GROQ_API_KEY or GOOGLE_API_KEY; DATABASE_URL optional
uv sync
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
uv run pytest
```

Frontend (Node 20+):

```
cd frontend
npm install
npm run dev               # http://localhost:5173
```

Without `DATABASE_URL`, conversation checkpoints are kept in memory and lost on restart.

## Data and privacy

All examples in this repository are synthetic. Research cites public sources by URL; source files, private notes and personal details are not committed.
