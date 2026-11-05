"""Pydantic request and response models for the HTTP API."""

from typing import Any

from pydantic import BaseModel, Field

# Thread ids name the upload folder, so only safe characters are allowed (no path tricks).
THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{1,100}$"


class ChatRequest(BaseModel):
    """A user message sent to one conversation thread."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    message: str = Field(min_length=1, max_length=8000)


class ResumeRequest(BaseModel):
    """The user's answer to a paused step: policy facts (O3) or the submission pack approval."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    approved: bool
    corrections: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """The agent's turn result for that thread.

    Attributes:
        reply: Latest assistant text; empty while the run is paused for confirmation.
        pending: Confirmation the user must answer via /api/resume, or None.
        onboarding: {"complete": bool, "missing": [...]} from O2.
        claim: Claim review from C1 (stage, checklist, issues, query, decision), plus payment from P1 once decided.
        documents: Document records (uploaded and connector-read), without server file paths.
        actions: Next-step buttons derived from state (empty while a card waits for an answer).
        notifications: In-app notices (insurer updates, reminders, warnings).
        submission: Submission route and status, or None.
        connection: Connected insurer account status ({"status", "linked_at"}), or None.
        history: Conversation as [{"role": "user" | "agent", "text"}]; only on GET /api/thread.
        answers: Hydrated form fields (members, claimType, patientName) from saved policies and claim_info.
        authority: The caregiver's authority record with its current status, or None (DEV-025).
        audit: Who did what and when, newest first, at most 50 entries (DEV-025).
        household: Confirmed policies, the one this claim goes to, the round and earlier rounds (DEV-024).
        dispute: Where the grievance and Ombudsman route stands, or None (DEV-026).
    """

    thread_id: str
    reply: str
    pending: dict[str, Any] | None = None
    onboarding: dict[str, Any] | None = None
    claim: dict[str, Any] | None = None
    documents: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    submission: dict[str, Any] | None = None
    connection: dict[str, Any] | None = None
    history: list[dict[str, str]] | None = None
    answers: dict[str, Any] = Field(default_factory=dict)
    authority: dict[str, Any] | None = None
    audit: list[dict[str, Any]] = Field(default_factory=list)
    household: dict[str, Any] | None = None
    dispute: dict[str, Any] | None = None


class ActionRequest(BaseModel):
    """A next-step button press. data carries form fields or the button's own data (a document or policy id)."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    action: str = Field(pattern=r"^[a-z_]{1,40}$")
    data: dict[str, str] = Field(default_factory=dict, max_length=5)


class ConnectionRequest(BaseModel):
    """The connection code shown on the connector page after the user approved access."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class AuthorityRequest(BaseModel):
    """A caregiver's authority to act for the patient (DEV-025). Proof is an uploaded document, by id."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    representative_name: str = Field(min_length=2, max_length=120)
    basis: str = Field(pattern=r"^[a-z_]{1,40}$")
    proof_doc_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    scope: list[str] = Field(min_length=1, max_length=4)
    expires_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ThreadRequest(BaseModel):
    """A request that only names the thread."""

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)


class HealthResponse(BaseModel):
    """Service status: database is 'ok', 'memory' or an error string."""

    status: str
    database: str
    llm_provider: str
