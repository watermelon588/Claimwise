"""FastAPI main application assembling all mock external services on port 8100."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from mocks.config import settings
from mocks.db import init_db
from mocks.clock import router as clock_router, get_current_time_iso
from mocks.faults import router as faults_router, apply_ingress_faults
from mocks.events import router as events_router
from mocks.routers.admin import router as admin_router
from mocks.routers.payer import router as payer_router
from mocks.routers.hospital import router as hospital_router
from mocks.routers.bank import router as bank_router
from mocks.routers.grievance import router as grievance_router
from mocks.services.scenarios import seed_base_entities
from mocks.db import get_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup handler ensuring tables and seed data exist."""
    init_db()
    conn = get_connection()
    try:
        seed_base_entities(conn)
        conn.commit()
    finally:
        conn.close()
    yield


app = FastAPI(
    title="Claimwise External Systems Mocks",
    description="Standalone mock services for Insurer/TPA (M1), Hospital (M2), Bank (M3), and Grievance/Ombudsman (M4).",
    version="0.1.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def faults_middleware(request: Request, call_next):
    """Intercept requests to apply configured latency or simulated error faults."""
    # Skip faults on administrative control endpoints
    if not request.url.path.startswith("/admin") and not request.url.path.startswith("/docs"):
        await apply_ingress_faults()
    response = await call_next(request)
    return response


# Include Routers
app.include_router(admin_router)
app.include_router(clock_router)
app.include_router(faults_router)
app.include_router(events_router)
app.include_router(payer_router)
app.include_router(hospital_router)
app.include_router(bank_router)
app.include_router(grievance_router)


@app.get("/", response_class=HTMLResponse)
def index():
    """Minimal status dashboard for mock services."""
    now = get_current_time_iso()
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Claimwise External Systems (MOCK)</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                margin: 40px;
                background-color: #f8fafc;
                color: #1e293b;
            }}
            .card {{
                background: white;
                border-radius: 8px;
                padding: 24px;
                max-width: 800px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                border-top: 6px solid rgb(248, 179, 0);
            }}
            h1 {{ color: #0f172a; margin-top: 0; }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                background: rgb(248, 179, 0);
                color: #1e293b;
                font-weight: bold;
                border-radius: 4px;
                font-size: 12px;
                margin-bottom: 12px;
            }}
            .service-list {{ list-style-type: none; padding-left: 0; }}
            .service-list li {{ padding: 8px 0; border-bottom: 1px solid #e2e8f0; }}
            a {{ color: #0284c7; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            pre {{ background: #f1f5f9; padding: 12px; border-radius: 4px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">CLAIMWISE MOCK SERVICES v0.1.0</span>
            <h1>External Systems Mock Server</h1>
            <p><strong>Virtual Clock:</strong> <code>{now}</code></p>
            <p>All endpoints enforce mock isolation, integer paise arithmetic, and deterministic responses.</p>

            <h3>Active Routers:</h3>
            <ul class="service-list">
                <li><strong>M1 Payer:</strong> <code>/payer/policies</code>, <code>/payer/claims</code>, <code>/payer/eligibility</code></li>
                <li><strong>M2 Hospital:</strong> <code>/hospital/admissions</code>, <code>/hospital/documents</code></li>
                <li><strong>M3 Bank:</strong> <code>/bank/accounts/ACC-001/statement</code></li>
                <li><strong>M4 Grievance:</strong> <code>/grievance/grievances</code>, <code>/grievance/ombudsman</code></li>
                <li><strong>Admin & Clock:</strong> <code>/admin/clock</code>, <code>/admin/faults</code>, <code>/admin/scenarios</code></li>
                <li><strong>Event Stream:</strong> <code>/events</code></li>
            </ul>

            <p><a href="/docs" target="_blank">&rarr; Interactive Swagger / OpenAPI Documentation</a></p>
        </div>
    </body>
    </html>
    """
