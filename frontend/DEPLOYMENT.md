# Claimwise deployment

## Vercel frontend

Use the `frontend` directory as the Vercel project root. Choose **Vite** and **Node.js 22.x**. [vercel.json](vercel.json) defines `npm ci`, `npm run build`, and `dist`. It also makes direct navigation and refresh work for `/app`, `/mocks`, `/policy`, `/privacy`, and `/terms`. [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite)

Before using the full demo, replace the two `.example.invalid` origins in [vercel.json](vercel.json) with the HTTPS URLs of your hosted services. Keep the path suffixes as written.

| Browser URL | Hosted destination |
| --- | --- |
| `/api/health` | Backend `/api/health` |
| `/api/chat/stream` | Backend `/api/chat/stream` |
| `/mock-api/admin/overview` | Mock service `/admin/overview` |
| `/mock-api/bank/accounts/ACC-001/statement.pdf` | Mock service `/bank/accounts/ACC-001/statement.pdf` |

The browser uses the Vercel origin for both services. The rewrites preserve request methods and route parameters, and disable caching for API responses. The landing and informational pages can be previewed before replacing the placeholder origins. [Vercel rewrites](https://vercel.com/docs/routing/rewrites)

From the repository root, the manual preview command is:

```powershell
cd frontend
npx vercel deploy
```

Use the Vercel CLI from that folder for a local upload without connecting GitHub. Keep service secrets in the Python host settings. The optional `VITE_CLAIMWISE_DEMO_URL` is a public video URL embedded at build time. [Vercel CLI deployment](https://vercel.com/docs/cli/deploy)

## Backend and mock hosting

**Render** supports two native Python Web Services. Create a service per directory, select Python 3.13, and use the existing `uv.lock` files. Use manual deploys if you later connect a repository. [Render FastAPI](https://render.com/docs/deploy-fastapi) · [Render uv setup](https://render.com/docs/uv-version) · [Python version settings](https://render.com/docs/python-version)

| Setting | Claimwise backend | Mock providers |
| --- | --- | --- |
| Service root | `backend` | `mocks` |
| Build command | `uv sync --locked --no-dev` | `uv sync --locked --no-dev` |
| Start command | `uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `uv run --no-sync uvicorn mocks.main:app --host 0.0.0.0 --port $PORT` |
| Health URL | `/api/health` | `/` |
| Persistent storage | Neon for checkpoints and a disk for upload files | A disk for SQLite and generated PDFs |

For a durable demo, attach a disk at `/var/data` to each service. Render persistent disks require paid services. A disposable demo can use ephemeral storage, with uploaded files and mock state reset on service restarts or redeploys. Keep each Python service at one instance for this prototype. [Render persistent disks](https://render.com/docs/disks)

| Service | Environment settings |
| --- | --- |
| Backend | `DATABASE_URL` for a dedicated Neon demo database, `UPLOAD_DIR=/var/data/uploads`, and `GOOGLE_API_KEY` and/or `GROQ_API_KEY` for the enabled model providers. |
| Mock | `MOCK_DB_PATH=/var/data/mock.db`, `DOCS_STORAGE_PATH=/var/data/generated_docs`. For signed demo webhooks, set `CLAIMWISE_WEBHOOK_URL` to the backend HTTPS origin plus `/api/webhooks/mock` and set the same private `MOCK_WEBHOOK_SECRET` on both services. |

**Railway** is an alternative if you want to upload the Python source directly. Deploy each directory to a separate service with the CLI and use the same Uvicorn app modules and a persistent volume per service. [Railway local upload](https://docs.railway.com/cli/up) · [Railway volumes](https://docs.railway.com/volumes)

### Demo scope

The two Python services support the claim workspace's manual workflows and the Mock Console. Connected submission and polling through a provider grant also require the separate [connector gateway](../docs/05-technical/provider-connectors.md). That gateway currently targets a loopback mock address and accepts loopback hostnames. Hosting that flow requires a reachable mock address, an allowed gateway hostname, and the backend's connector settings.

Use synthetic records for the hosted demo. The current guest workspace exposes thread history and the mock service exposes test mutations. Real claim data requires authenticated access and per-user authorization, including at the direct service origins.

### Smoke check after deployment

- Load the Vercel preview, then refresh each of the five deep links.
- Open `/api/health` and `/mock-api/admin/overview` on the preview domain. Expect JSON from the matching service.
- In a synthetic case, upload a sample document and confirm chat streams. In Mock Console, download a generated PDF.
