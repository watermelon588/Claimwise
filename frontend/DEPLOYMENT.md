# Claimwise deployment

The [hosting guide](../docs/07-delivery/hosting.md) covers the whole demo: this frontend on Vercel (project root `frontend`, config in [vercel.json](vercel.json)), and the agent API, mock providers and connector gateway on Render ([render.yaml](../render.yaml)).

[vercel.json](vercel.json) builds with `npm ci` and `npm run build` into `dist`, makes direct navigation work for `/app`, `/mocks`, `/policy`, `/privacy` and `/terms`, and forwards these paths with caching disabled:

| Browser path | Destination |
| --- | --- |
| `/api/*` | `claimwise-backend` `/api/*` |
| `/mock-api/*` | `claimwise-mocks` `/*` |
| `/connector-api/api/connectors*` | `claimwise-connectors` `/api/connectors*` |

If Render gives a service a different hostname, update it here and push.

Use synthetic records only. The guest workspace and the mock admin routes need authenticated access and per-user authorization before any real claim data.
