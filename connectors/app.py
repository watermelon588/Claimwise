"""Standalone demo gateway for verified sessions, provider consent and agent reads."""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import re
import secrets
from time import monotonic
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Path as PathParam, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .providers import (
    ClaimSubmission, ProviderError, QueryAnswer, TOOLS, answer_query, fetch_tool, find_claims, read_submitted_claim,
    submit_claim,
)

SESSION_COOKIE = "claimwise_connector_demo"
SESSION_SECONDS = 3600
CLAIM_ID = r"^CLM-[A-Z0-9]{1,16}$"
REFERENCE = r"^[A-Za-z0-9_-]{8,80}$"  # idempotency keys and client references
PROVIDERS = {tool.provider: (name, tool) for name, tool in TOOLS.items()}
THREAD_ID = r"^[A-Za-z0-9_-]{1,100}$"
EMAIL_TOOL = {
    "name": "case_email", "provider": "email", "label": "Case email",
    "scope": "email.notify", "description": "Deliver case updates to the synthetic inbox",
}
MAIL_SUBJECTS = {"update": "There is an update on your claim", "reminder": "Your claim needs attention"}


@dataclass(frozen=True)
class DemoKeys:
    """Independent codes for demo onboarding, provider sign-ins and server access."""

    onboarding: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    agent: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    email: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    providers: dict[str, str] = field(
        default_factory=lambda: {provider: secrets.token_urlsafe(18) for provider in PROVIDERS}
    )

    @classmethod
    def from_env(cls) -> tuple["DemoKeys", list[tuple[str, str]]]:
        """Read hosted codes from the environment; generate any that are unset.

        Hosting has no terminal to read printed codes from, so the operator sets CONNECTOR_AGENT_KEY (the same
        value as the backend's), CONNECTOR_ONBOARDING_CODE, CONNECTOR_EMAIL_CODE and CONNECTOR_<PROVIDER>_CODE.

        Returns:
            The keys, and (label, value) pairs for the generated ones only, so configured secrets never reach logs.
        """
        made, generated = cls(), []

        def pick(var: str, label: str, fallback: str) -> str:
            value = os.environ.get(var, "").strip()
            if not value:
                generated.append((label, fallback))
            return value or fallback

        keys = cls(
            onboarding=pick("CONNECTOR_ONBOARDING_CODE", "onboarding code", made.onboarding),
            agent=pick("CONNECTOR_AGENT_KEY", "server bearer key", made.agent),
            email=pick("CONNECTOR_EMAIL_CODE", "email sign-in code", made.email),
            providers={p: pick(f"CONNECTOR_{p.upper()}_CODE", f"{p} sign-in code", code) for p, code in made.providers.items()},
        )
        return keys, generated


def allowed(var: str, defaults: list[str]) -> list[str]:
    """Defaults plus the comma-separated values of an environment variable."""
    return defaults + [v.strip() for v in os.environ.get(var, "").split(",") if v.strip()]


@dataclass
class Session:
    """A verified demo case with its own browser credential and provider grants."""

    browser_key: str
    expires_at: float
    grants: dict[str, str] = field(default_factory=dict)
    thread_id: str | None = None
    email_since: datetime | None = None
    inbox: dict[str, dict] = field(default_factory=dict)


class Verification(BaseModel):
    """Accept a demo code without permitting identity or resource overrides."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=128)


class Consent(Verification):
    """Require affirmative read consent in addition to the provider sign-in code."""

    approved: StrictBool


class MailNotice(BaseModel):
    """A minimized notification for the synthetic inbox."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    at: datetime
    kind: Literal["update", "reminder"]


class MailBatch(BaseModel):
    """Limit the number of notices accepted per delivery."""

    model_config = ConfigDict(extra="forbid")
    notices: list[MailNotice] = Field(max_length=50)


def workspace_thread(request: Request) -> str | None:
    """Validate the requested browser workspace and derive its cookie namespace."""
    thread = request.headers.get("x-claimwise-thread")
    if thread is not None and not re.fullmatch(THREAD_ID, thread):
        raise fail(422, "INVALID_THREAD")
    return thread


def cookie_name(thread: str | None) -> str:
    """Keep consent for one claim separate from consent for another claim in the same browser."""
    return f"{SESSION_COOKIE}_{thread}" if thread else SESSION_COOKIE


def matches(presented: str, expected: str) -> bool:
    """Compare credentials without exceptions on non-ASCII input."""
    return secrets.compare_digest(presented.encode(), expected.encode())


def fail(status: int, code: str) -> HTTPException:
    """Return a stable error without upstream text or submitted credentials."""
    return HTTPException(status, detail={"code": code})


def create_app(keys: DemoKeys | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Create a local-only gateway, with optional in-process test credentials and transport."""
    sessions: dict[str, Session] = {}
    credentials, generated = (keys, []) if keys else DemoKeys.from_env()
    # Hosted: the frontend's origin (it proxies /connector-api here) and Render's own hostname are allowed too.
    origins = allowed("CONNECTOR_ALLOWED_ORIGINS", [])
    hosts = allowed("CONNECTOR_ALLOWED_HOSTS", ["127.0.0.1", "localhost"] + (
        [os.environ["RENDER_EXTERNAL_HOSTNAME"]] if os.environ.get("RENDER_EXTERNAL_HOSTNAME") else []))
    mock_url = os.environ.get("CLAIMWISE_MOCK_URL") or f"http://127.0.0.1:{int(os.environ.get('CLAIMWISE_MOCK_PORT', '8100'))}"

    @asynccontextmanager
    async def lifespan(gateway: FastAPI):
        """Enable the synthetic demo explicitly and open one pooled client to the mock providers."""
        if keys is None:
            if os.environ.get("CLAIMWISE_CONNECTOR_DEMO") != "1":
                raise RuntimeError("Set CLAIMWISE_CONNECTOR_DEMO=1 to enable the local synthetic demo")
            for label, value in generated:  # only generated codes; configured ones stay out of the logs
                print(f"Local demo {label}: {value}", flush=True)
        async with httpx.AsyncClient(
            base_url=mock_url, transport=transport, timeout=5, follow_redirects=False, trust_env=False,
        ) as client:
            gateway.state.provider_client = client
            yield

    gateway = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    gateway.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @gateway.middleware("http")
    async def protect_response(request: Request, call_next):
        """Require same-origin (or configured frontend) browser mutations and mark all responses non-cacheable."""
        origin = request.headers.get("origin")
        same = origin == str(request.base_url).rstrip("/") or origin in origins
        if request.method in {"POST", "DELETE"} and origin and not same:
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
        thread = workspace_thread(request)
        case_id, _, browser_key = request.cookies.get(cookie_name(thread), "").partition(".")
        session = active_case(case_id)
        if session.thread_id != thread or not matches(browser_key, session.browser_key):
            raise fail(401, "VERIFICATION_REQUIRED")
        return case_id, session

    def agent_case(request: Request, case_id: str) -> Session:
        """Require the server credential before looking up any case or grants."""
        if not matches(request.headers.get("authorization", ""), f"Bearer {credentials.agent}"):
            raise fail(401, "SERVER_AUTH_REQUIRED")
        return active_case(case_id)

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
        thread = workspace_thread(request)
        session = Session(secrets.token_urlsafe(32), now + SESSION_SECONDS, thread_id=thread)
        sessions[case_id] = session
        response.set_cookie(
            cookie_name(thread), f"{case_id}.{session.browser_key}", max_age=SESSION_SECONDS,
            httponly=True, samesite="strict",
        )
        return {"case_id": case_id}

    @gateway.delete("/api/connectors/session", status_code=204)
    async def sign_out(request: Request, response: Response):
        """End the verified case and invalidate all of its provider grants."""
        case_id, _ = browser_case(request)
        del sessions[case_id]
        response.delete_cookie(cookie_name(workspace_thread(request)))

    @gateway.get("/api/connectors")
    async def catalog(request: Request):
        """Show provider scopes and the current verified browser's connection status."""
        case_id, session = browser_case(request)
        providers = [tool.descriptor(name) for name, tool in TOOLS.items()]
        if session.thread_id:
            providers.append(EMAIL_TOOL)
        return {
            "case_id": case_id,
            "providers": [{**tool, "connected": tool["provider"] in session.grants} for tool in providers],
        }

    @gateway.post("/api/connectors/{provider}")
    async def connect(provider: str, body: Consent, request: Request):
        """Grant a provider scope only after verification, sign-in and explicit approval."""
        _, session = browser_case(request)
        if provider not in PROVIDERS and not (provider == "email" and session.thread_id):
            raise fail(404, "UNKNOWN_PROVIDER")
        code = credentials.email if provider == "email" else credentials.providers.get(provider)
        if not code or not matches(body.code, code):
            raise fail(403, "INVALID_PROVIDER_CODE")
        if not body.approved:
            raise fail(403, "CONSENT_REQUIRED")
        if provider not in session.grants:
            session.grants[provider] = secrets.token_urlsafe(18)
            if provider == "email":
                session.email_since = datetime.now(timezone.utc)
        return {"provider": provider, "connected": True}

    @gateway.delete("/api/connectors/{provider}", status_code=204)
    async def disconnect(provider: str, request: Request):
        """Revoke one provider without affecting the other grants."""
        _, session = browser_case(request)
        if provider not in PROVIDERS and not (provider == "email" and session.thread_id):
            raise fail(404, "UNKNOWN_PROVIDER")
        session.grants.pop(provider, None)
        if provider == "email":
            session.email_since = None
            session.inbox.clear()

    @gateway.get("/agent/cases/{case_id}/tools")
    async def discover(case_id: str, request: Request):
        """Return only the tools currently approved for the trusted caller's case."""
        session = agent_case(request, case_id)
        if session.thread_id != workspace_thread(request):
            raise fail(403, "WRONG_WORKSPACE")
        tools = [tool.descriptor(name) for name, tool in TOOLS.items() if tool.provider in session.grants]
        if "email" in session.grants:
            tools.append(EMAIL_TOOL)
        return {"tools": tools}

    @gateway.get("/api/connectors/inbox")
    async def inbox(request: Request):
        """Return delivered demo mail only to the case's verified browser."""
        _, session = browser_case(request)
        if "email" not in session.grants:
            raise fail(403, "PROVIDER_NOT_CONNECTED")
        return {"messages": sorted(session.inbox.values(), key=lambda row: row["at"], reverse=True)}

    @gateway.get("/api/connectors/document")
    async def hospital_document(request: Request):
        """Read the approved hospital fixture for the verified browser."""
        case_id, session = browser_case(request)
        return await read_fixture(case_id, session, "read_discharge_summary", request)

    @gateway.post("/agent/cases/{case_id}/mail")
    async def deliver(case_id: str, body: MailBatch, request: Request):
        """Deliver post-consent notices once, without names, amounts, or attachments."""
        session = agent_case(request, case_id)
        if not session.email_since or "email" not in session.grants:
            raise fail(403, "PROVIDER_NOT_CONNECTED")
        for notice in body.notices:
            if notice.at.tzinfo is None or notice.at < session.email_since:
                continue
            session.inbox.setdefault(notice.id, {
                "id": notice.id, "at": notice.at.isoformat(), "subject": MAIL_SUBJECTS[notice.kind],
                "body": "Open your Claimwise case to see the latest update.",
            })
        if len(session.inbox) > 100:
            retained = sorted(session.inbox.values(), key=lambda row: row["at"], reverse=True)[:100]
            session.inbox = {row["id"]: row for row in retained}
        return {"delivered": True}

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

    @gateway.post("/agent/cases/{case_id}/claims/{claim_id}/documents")
    async def answer(case_id: str, body: QueryAnswer, request: Request, claim_id: str = PathParam(pattern=CLAIM_ID)):
        """Write tool: send the documents answering an open query, after the user approved the list in Claimwise."""
        grant = claims_grant(request, case_id)
        api_key = os.environ.get("CLAIMWISE_MOCK_API_KEY", "claimwise-demo-key")
        try:
            data = await answer_query(request.app.state.provider_client, claim_id, body, api_key)
        except ProviderError as exc:
            raise fail(exc.status, exc.code) from exc
        still_granted(case_id, grant)
        return sourced("answer_query", data)

    @gateway.get("/agent/cases/{case_id}/tools/{name}")
    async def invoke(case_id: str, name: str, request: Request):
        """Read the approved fixture, recheck consent after I/O, and add source metadata."""
        return await read_fixture(case_id, agent_case(request, case_id), name, request)

    async def read_fixture(case_id: str, session: Session, name: str, request: Request):
        """Share the same grant enforcement for agent and browser reads."""
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
