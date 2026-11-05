"""Standalone demo gateway for verified sessions, provider consent and agent reads."""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
import secrets
from time import monotonic

import httpx
from fastapi import FastAPI, Header, HTTPException, Path as PathParam, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .providers import (
    ClaimSubmission, ProviderError, TOOLS, fetch_tool, find_claims, read_submitted_claim, submit_claim,
)

SESSION_COOKIE = "claimwise_connector_demo"
SESSION_SECONDS = 3600
CLAIM_ID = r"^CLM-[A-Z0-9]{1,16}$"
REFERENCE = r"^[A-Za-z0-9_-]{8,80}$"  # idempotency keys and client references
PROVIDERS = {tool.provider: (name, tool) for name, tool in TOOLS.items()}


@dataclass(frozen=True)
class DemoKeys:
    """Independent codes for demo onboarding, provider sign-ins and server access."""

    onboarding: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    agent: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    providers: dict[str, str] = field(
        default_factory=lambda: {provider: secrets.token_urlsafe(18) for provider in PROVIDERS}
    )


@dataclass
class Session:
    """A verified demo case with its own browser credential and provider grants."""

    browser_key: str
    expires_at: float
    grants: dict[str, str] = field(default_factory=dict)


class Verification(BaseModel):
    """Accept a demo code without permitting identity or resource overrides."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=128)


class Consent(Verification):
    """Require affirmative read consent in addition to the provider sign-in code."""

    approved: StrictBool


def matches(presented: str, expected: str) -> bool:
    """Compare credentials without exceptions on non-ASCII input."""
    return secrets.compare_digest(presented.encode(), expected.encode())


def fail(status: int, code: str) -> HTTPException:
    """Return a stable error without upstream text or submitted credentials."""
    return HTTPException(status, detail={"code": code})


def create_app(keys: DemoKeys | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Create a local-only gateway, with optional in-process test credentials and transport."""
    sessions: dict[str, Session] = {}
    credentials = keys or DemoKeys()

    @asynccontextmanager
    async def lifespan(gateway: FastAPI):
        """Enable the synthetic demo explicitly and open one pooled loopback client."""
        if keys is None:
            if os.environ.get("CLAIMWISE_CONNECTOR_DEMO") != "1":
                raise RuntimeError("Set CLAIMWISE_CONNECTOR_DEMO=1 to enable the local synthetic demo")
            print("Local demo onboarding code:", credentials.onboarding, flush=True)
            for provider, code in credentials.providers.items():
                print(f"Local demo {provider} sign-in code: {code}", flush=True)
            print("Local demo server bearer key:", credentials.agent, flush=True)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{int(os.environ.get('CLAIMWISE_MOCK_PORT', '8100'))}",
            transport=transport, timeout=5, follow_redirects=False, trust_env=False,
        ) as client:
            gateway.state.provider_client = client
            yield

    gateway = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    gateway.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @gateway.middleware("http")
    async def protect_response(request: Request, call_next):
        """Require same-origin browser mutations and mark all responses non-cacheable."""
        origin = request.headers.get("origin")
        if request.method in {"POST", "DELETE"} and origin and origin != str(request.base_url).rstrip("/"):
            response = JSONResponse({"detail": {"code": "ORIGIN_DENIED"}}, status_code=403)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @gateway.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        """Suppress the submitted values in framework validation responses."""
        return JSONResponse({"detail": {"code": "INVALID_REQUEST"}}, status_code=422)

    def active_case(case_id: str) -> Session:
        """Resolve the live server-side case record or reject an expired or unknown case."""
        session = sessions.get(case_id)
        if session is None or session.expires_at <= monotonic():
            sessions.pop(case_id, None)
            raise fail(401, "VERIFICATION_REQUIRED")
        return session

    def browser_case(request: Request) -> tuple[str, Session]:
        """Authenticate a browser using the cookie's case reference and separate secret."""
        case_id, _, browser_key = request.cookies.get(SESSION_COOKIE, "").partition(".")
        session = active_case(case_id)
        if not matches(browser_key, session.browser_key):
            raise fail(401, "VERIFICATION_REQUIRED")
        return case_id, session

    def agent_case(request: Request, case_id: str) -> Session:
        """Require the server credential before looking up any case or grants."""
        if not matches(request.headers.get("authorization", ""), f"Bearer {credentials.agent}"):
            raise fail(401, "SERVER_AUTH_REQUIRED")
        return active_case(case_id)

    @gateway.get("/", response_class=HTMLResponse)
    async def page():
        """Serve the local connector page with a per-response script and style nonce."""
        nonce = secrets.token_urlsafe(24)
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        policy = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return HTMLResponse(html.replace("__NONCE__", nonce), headers={"Content-Security-Policy": policy})

    @gateway.post("/api/connectors/session", status_code=201)
    async def verify(body: Verification, request: Request, response: Response):
        """Create a verified synthetic case after checking the demo onboarding code."""
        if not matches(body.code, credentials.onboarding):
            raise fail(403, "INVALID_ONBOARDING_CODE")

        # Replacing an authenticated browser session must also retire its old grants.
        try:
            old_case_id, _ = browser_case(request)
        except HTTPException:
            pass
        else:
            del sessions[old_case_id]
        now = monotonic()
        for case_id in tuple(sessions):
            if sessions[case_id].expires_at <= now:
                del sessions[case_id]
        if len(sessions) >= 64:
            raise fail(503, "DEMO_SESSION_LIMIT")
        case_id = secrets.token_urlsafe(18)
        session = Session(secrets.token_urlsafe(32), now + SESSION_SECONDS)
        sessions[case_id] = session
        response.set_cookie(
            SESSION_COOKIE, f"{case_id}.{session.browser_key}", max_age=SESSION_SECONDS,
            httponly=True, samesite="strict",
        )
        return {"case_id": case_id}

    @gateway.delete("/api/connectors/session", status_code=204)
    async def sign_out(request: Request, response: Response):
        """End the verified case and invalidate all of its provider grants."""
        case_id, _ = browser_case(request)
        del sessions[case_id]
        response.delete_cookie(SESSION_COOKIE)

    @gateway.get("/api/connectors")
    async def catalog(request: Request):
        """Show provider scopes and the current verified browser's connection status."""
        case_id, session = browser_case(request)
        return {
            "case_id": case_id,
            "providers": [
                {**tool.descriptor(name), "connected": tool.provider in session.grants}
                for name, tool in TOOLS.items()
            ],
        }

    @gateway.post("/api/connectors/{provider}")
    async def connect(provider: str, body: Consent, request: Request):
        """Grant a provider scope only after verification, sign-in and explicit approval."""
        _, session = browser_case(request)
        if provider not in PROVIDERS:
            raise fail(404, "UNKNOWN_PROVIDER")
        if not matches(body.code, credentials.providers[provider]):
            raise fail(403, "INVALID_PROVIDER_CODE")
        if not body.approved:
            raise fail(403, "CONSENT_REQUIRED")
        session.grants.setdefault(provider, secrets.token_urlsafe(18))
        return {"provider": provider, "connected": True}

    @gateway.delete("/api/connectors/{provider}", status_code=204)
    async def disconnect(provider: str, request: Request):
        """Revoke one provider without affecting the other grants."""
        _, session = browser_case(request)
        if provider not in PROVIDERS:
            raise fail(404, "UNKNOWN_PROVIDER")
        session.grants.pop(provider, None)

    @gateway.get("/agent/cases/{case_id}/tools")
    async def discover(case_id: str, request: Request):
        """Return only the tools currently approved for the trusted caller's case."""
        session = agent_case(request, case_id)
        return {
            "tools": [
                tool.descriptor(name) for name, tool in TOOLS.items() if tool.provider in session.grants
            ],
        }

    def claims_grant(request: Request, case_id: str) -> str:
        """Server auth plus the TPA connection, which covers claim reads and approved submissions."""
        grant = agent_case(request, case_id).grants.get("tpa")
        if grant is None:
            raise fail(403, "PROVIDER_NOT_CONNECTED")
        return grant

    def still_granted(case_id: str, grant: str) -> None:
        """Recheck consent after provider I/O so a revocation in flight withholds the result."""
        if active_case(case_id).grants.get("tpa") != grant:
            raise fail(403, "PROVIDER_NOT_CONNECTED")

    def sourced(name: str, data) -> dict:
        """Wrap provider data with the same source metadata as the read tools."""
        retrieved_at = datetime.now(timezone.utc).isoformat()
        return {"source": {"provider": "tpa", "tool": name, "mock": True, "retrieved_at": retrieved_at}, "data": data}

    @gateway.post("/agent/cases/{case_id}/claims", status_code=201)
    async def submit(
        case_id: str, body: ClaimSubmission, request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=REFERENCE),
    ):
        """Write tool: submit a claim pack the user approved in Claimwise. Same key, same claim."""
        grant = claims_grant(request, case_id)
        api_key = os.environ.get("CLAIMWISE_MOCK_API_KEY", "claimwise-demo-key")
        try:
            data = await submit_claim(request.app.state.provider_client, body, idempotency_key, api_key)
        except ProviderError as exc:
            raise fail(exc.status, exc.code) from exc
        still_granted(case_id, grant)
        return sourced("submit_claim", data)

    @gateway.get("/agent/cases/{case_id}/claims")
    async def lookup(case_id: str, request: Request, client_reference: str = Query(pattern=REFERENCE)):
        """Find claims by the caller client reference (lost-response recovery before any retry)."""
        grant = claims_grant(request, case_id)
        try:
            data = await find_claims(request.app.state.provider_client, client_reference)
        except ProviderError as exc:
            raise fail(exc.status, exc.code) from exc
        still_granted(case_id, grant)
        return sourced("find_claims", data)

    @gateway.get("/agent/cases/{case_id}/claims/{claim_id}")
    async def claim_status(case_id: str, request: Request, claim_id: str = PathParam(pattern=CLAIM_ID)):
        """Read status, queries, decision and payments of a submitted claim (monitoring)."""
        grant = claims_grant(request, case_id)
        try:
            data = await read_submitted_claim(request.app.state.provider_client, claim_id)
        except ProviderError as exc:
            raise fail(exc.status, exc.code) from exc
        still_granted(case_id, grant)
        return sourced("read_submitted_claim", data)

    @gateway.get("/agent/cases/{case_id}/tools/{name}")
    async def invoke(case_id: str, name: str, request: Request):
        """Read the approved fixture, recheck consent after I/O, and add source metadata."""
        session = agent_case(request, case_id)
        tool = TOOLS.get(name)
        if tool is None:
            raise fail(404, "UNKNOWN_TOOL")
        if request.url.query:
            raise fail(422, "TOOL_TAKES_NO_ARGUMENTS")
        grant = session.grants.get(tool.provider)
        if grant is None:
            raise fail(403, "PROVIDER_NOT_CONNECTED")
        try:
            data = await fetch_tool(request.app.state.provider_client, tool)
        except ProviderError as exc:
            raise fail(exc.status, exc.code) from exc

        # A revocation followed by re-approval must not release an older in-flight read.
        if active_case(case_id).grants.get(tool.provider) != grant:
            raise fail(403, "PROVIDER_NOT_CONNECTED")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        if isinstance(data, bytes):
            return Response(
                data, media_type="application/pdf",
                headers={
                    "Content-Disposition": 'attachment; filename="mock-discharge-summary.pdf"',
                    "X-Connector-Provider": tool.provider, "X-Connector-Tool": name,
                    "X-Connector-Mock": "true", "X-Connector-Retrieved-At": retrieved_at,
                },
            )
        return {
            "source": {"provider": tool.provider, "tool": name, "mock": True, "retrieved_at": retrieved_at},
            "data": data,
        }

    return gateway


app = create_app()
