"""Tool registry and response adapters for the loopback mock providers.

Four read tools take no arguments (fixture IDs come from the operator). One write tool, submit_claim,
sends a claim pack the user already approved. The claim lookups it needs (by client reference for
lost-response recovery, by claim ID for status monitoring) are covered by the same TPA consent.
"""

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Policy(BaseModel):
    """Coverage fields allowed into agent context. Currency values are in paise."""

    mock: Literal[True]
    id: Literal["POL-001"]
    policy_number: Literal["SURAKSHA-HEALTH-2026-001"]
    period_start: str
    period_end: str
    sum_insured: int
    balance_sum_insured: int
    room_rent_limit_per_day: int
    copay_percent: int
    deductible: int
    version: int


class ClaimQuery(BaseModel):
    """A deficiency request, including text supplied by the provider."""

    id: str
    raised_at: str | None = None
    answered_at: str | None = None
    due_at: str
    status: str
    items: list[dict[str, str]]


class ClaimDecision(BaseModel):
    """Claim decision facts with no internal document location."""

    outcome: str
    decided_at: str
    approved_amount: int
    rejection_reason: str | None
    policy_clause: str | None


class Credit(BaseModel):
    """A payment or credit reference, amount and source timestamp."""

    amount: int
    utr: str


class BankCredit(Credit):
    """The date the bank recorded a credit."""

    credited_at: str


class ClaimPayment(Credit):
    """The date the payer reported making a payment."""

    paid_at: str


class Claim(BaseModel):
    """Claim status, requests, decision and payment for the demo member."""

    mock: Literal[True]
    id: Literal["CLM-0001"]
    policy_id: Literal["POL-001"]
    member_id: Literal["MEM-01"]
    status: str
    claimed_amount: int
    version: int
    queries: list[ClaimQuery]
    decision: ClaimDecision | None
    payments: list[ClaimPayment]


class DecisionWithLines(ClaimDecision):
    """A decision on a submitted claim, with the per-line breakdown when the payer gives one."""

    line_decisions: list[dict] | None = None


class SubmittedClaim(BaseModel):
    """Status, queries, decision and payments for a claim submitted through submit_claim."""

    id: str = Field(pattern=r"^CLM-[A-Z0-9]{1,16}$")
    client_reference: str | None
    status: str
    claimed_amount: int
    version: int
    submitted_at: str | None
    queries: list[ClaimQuery]
    decision: DecisionWithLines | None
    payments: list[ClaimPayment]


class SubmissionLine(BaseModel):
    """One bill line in a submission, amount in paise."""

    model_config = ConfigDict(extra="forbid")
    head: str = Field(min_length=1, max_length=120)
    amount: int = Field(gt=0)


class SubmissionDocument(BaseModel):
    """Metadata of one document in the approved pack (the mock does not receive file bytes)."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=64)
    filename: str = Field(max_length=200)
    doc_type: str = Field(max_length=40)


class ClaimSubmission(BaseModel):
    """The approved claim pack in the payer submission shape. Amounts in paise."""

    model_config = ConfigDict(extra="forbid")
    client_reference: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    policy_number: str = Field(min_length=1, max_length=60)
    member_name: str = Field(min_length=1, max_length=120)
    acting_user: str | None = Field(default=None, max_length=120)  # representative acting for the member
    claim_type: Literal["reimbursement", "cashless"]
    admission_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    discharge_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    claimed_amount: int = Field(gt=0)
    line_items: list[SubmissionLine] = Field(default_factory=list, max_length=200)
    documents: list[SubmissionDocument] = Field(default_factory=list, max_length=50)


class QueryAnswer(BaseModel):
    """Documents that answer the open insurer query on a claim (metadata only, like a submission)."""

    model_config = ConfigDict(extra="forbid")
    documents: list[SubmissionDocument] = Field(min_length=1, max_length=20)


# Payer refusals that are safe to pass on by code, because the claimant can act on them.
PAYER_REFUSALS = {"POLICY_NOT_FOUND", "MEMBER_NOT_COVERED", "NOT_AUTHORISED_REPRESENTATIVE"}


class Account(BaseModel):
    """Match the configured demo account and exclude holder details."""

    id: Literal["ACC-001"]


class Statement(BaseModel):
    """Credits to the dedicated synthetic account."""

    mock: Literal[True]
    account: Account
    credits: list[BankCredit]


@dataclass(frozen=True)
class Tool:
    """One approved scope with a fixed upstream resource and output contract."""

    provider: str
    label: str
    scope: str
    description: str
    path: str
    schema: type[BaseModel] | None

    def descriptor(self, name: str) -> dict:
        """Return UI and agent metadata for the registry key, without upstream routing."""
        return {
            "name": name, "provider": self.provider, "label": self.label,
            "scope": self.scope, "description": self.description,
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_media_type": "application/json" if self.schema else "application/pdf",
        }


# Demo resource IDs come from operator-controlled fixtures, never from the model or browser.
TOOLS = {
    "read_policy": Tool(
        "insurer", "Suraksha General Insurance", "policy.read", "Coverage dates and limits",
        "/payer/policies/SURAKSHA-HEALTH-2026-001", Policy,
    ),
    "read_claim": Tool(
        "tpa", "Medivista TPA", "claim.read claim.submit",
        "Claim status, requests, decision and payments; submit a claim pack you approved",
        "/payer/claims/CLM-0001", Claim,
    ),
    "read_discharge_summary": Tool(
        "hospital", "Sunrise Hospital", "discharge_summary.read", "Discharge summary PDF",
        "/hospital/documents/DOC-DS-ADM-001.pdf", None,
    ),
    "read_bank_credits": Tool(
        "bank", "Bharat Demo Bank", "credits.read", "Credits in the synthetic claim account",
        "/bank/accounts/ACC-001/statement", Statement,
    ),
}


class ProviderError(Exception):
    """An upstream failure with a safe gateway status and error code."""

    def __init__(self, status: int, code: str):
        """Store the public status and code without the upstream response body."""
        super().__init__(code)
        self.status = status
        self.code = code


async def fetch_tool(client: httpx.AsyncClient, tool: Tool) -> dict | bytes:
    """Fetch a registry entry, bound response size, and return validated facts or PDF bytes."""
    media_type = "application/json" if tool.schema else "application/pdf"
    limit = 512 * 1024 if tool.schema else 5 * 1024 * 1024
    payload = bytearray()
    try:
        # A total deadline also limits slow streams that keep individual reads alive.
        async with asyncio.timeout(8), client.stream("GET", tool.path) as response:
            if response.status_code == 404:
                raise ProviderError(404, "PROVIDER_RECORD_NOT_FOUND")
            if response.status_code in (429, 503):
                raise ProviderError(503, "PROVIDER_UNAVAILABLE")
            if response.status_code != 200:
                raise ProviderError(502, "PROVIDER_READ_FAILED")
            if response.headers.get("content-type", "").split(";")[0].strip() != media_type:
                raise ProviderError(502, "INVALID_PROVIDER_RESPONSE")
            async for chunk in response.aiter_bytes(chunk_size=16 * 1024):
                if len(payload) + len(chunk) > limit:
                    raise ProviderError(502, "INVALID_PROVIDER_RESPONSE")
                payload.extend(chunk)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ProviderError(504, "PROVIDER_TIMEOUT") from exc
    except httpx.RequestError as exc:
        raise ProviderError(503, "PROVIDER_UNAVAILABLE") from exc

    # The schemas drop fields outside the approved purpose, including member DOBs and account details.
    if tool.schema:
        try:
            data = tool.schema.model_validate_json(payload, strict=True)
        except ValidationError as exc:
            raise ProviderError(502, "INVALID_PROVIDER_RESPONSE") from exc
        return data.model_dump(exclude={"mock"})
    if not payload.startswith(b"%PDF-"):
        raise ProviderError(502, "INVALID_PROVIDER_RESPONSE")
    return bytes(payload)


async def call_payer(
    client: httpx.AsyncClient, method: str, path: str, *, body: dict | None = None,
    headers: dict | None = None, params: dict | None = None,
) -> httpx.Response:
    """Call the mock payer with a total deadline and map transport failures to safe gateway errors."""
    try:
        async with asyncio.timeout(8):
            response = await client.request(method, path, json=body, headers=headers, params=params)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ProviderError(504, "PROVIDER_TIMEOUT") from exc
    except httpx.RequestError as exc:
        raise ProviderError(503, "PROVIDER_UNAVAILABLE") from exc
    if len(response.content) > 512 * 1024:
        raise ProviderError(502, "INVALID_PROVIDER_RESPONSE")
    return response


def payer_refusal(response: httpx.Response) -> str | None:
    """The payer error code when it is one the claimant can act on, else None."""
    try:
        code = response.json()["detail"]["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None
    return code if code in PAYER_REFUSALS else None


async def submit_claim(client: httpx.AsyncClient, submission: ClaimSubmission, key: str, api_key: str) -> dict:
    """Submit an approved claim with an idempotency key; a retry with the same key returns the same claim.

    Raises:
        ProviderError: 422 with the payer refusal code; 502 PROVIDER_SUBMIT_UNCONFIRMED when the outcome
        is unclear (the claim may exist, so the caller must look it up by client reference before
        retrying); 503 or 504 when the payer could not be reached.
    """
    response = await call_payer(
        client, "POST", "/payer/claims", body=submission.model_dump(),
        headers={"Idempotency-Key": key, "X-Api-Key": api_key},
    )
    if response.status_code in (200, 201):
        try:
            data = response.json()
            return {k: data[k] for k in ("id", "client_reference", "status", "submitted_at")}
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(502, "INVALID_PROVIDER_RESPONSE") from exc
    refusal = payer_refusal(response)
    if refusal:
        raise ProviderError(422, refusal)
    raise ProviderError(502, "PROVIDER_SUBMIT_UNCONFIRMED")


async def find_claims(client: httpx.AsyncClient, client_reference: str) -> list[dict]:
    """Claims the payer holds for one client reference (checked before any retry)."""
    response = await call_payer(client, "GET", "/payer/claims", params={"client_reference": client_reference})
    if response.status_code != 200:
        raise ProviderError(502, "PROVIDER_READ_FAILED")
    try:
        return [
            {k: row.get(k) for k in ("id", "client_reference", "status", "submitted_at")}
            for row in response.json()
        ]
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProviderError(502, "INVALID_PROVIDER_RESPONSE") from exc


async def read_submitted_claim(client: httpx.AsyncClient, claim_id: str) -> dict:
    """Validated status, queries, decision and payments of one submitted claim."""
    response = await call_payer(client, "GET", f"/payer/claims/{claim_id}")
    if response.status_code == 404:
        raise ProviderError(404, "PROVIDER_RECORD_NOT_FOUND")
    if response.status_code != 200:
        raise ProviderError(502, "PROVIDER_READ_FAILED")
    try:
        return SubmittedClaim.model_validate_json(response.content).model_dump()
    except ValidationError as exc:
        raise ProviderError(502, "INVALID_PROVIDER_RESPONSE") from exc


async def answer_query(client: httpx.AsyncClient, claim_id: str, answer: QueryAnswer, api_key: str) -> dict:
    """Send the documents that answer the open query on one claim.

    Raises:
        ProviderError: 404 when the claim is unknown; 409 QUERY_NOT_OPEN when the payer has no open query
        (already answered or decided); 502 PROVIDER_ANSWER_UNCONFIRMED when the outcome is unclear (read the
        claim before sending again); 503 or 504 when the payer could not be reached.
    """
    response = await call_payer(client, "POST", f"/payer/claims/{claim_id}/documents", body=answer.model_dump(),
                                headers={"X-Api-Key": api_key})
    if response.status_code == 200:
        try:
            data = response.json()
            return {"claim_id": data["claim_id"], "status": data["status"]}
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(502, "INVALID_PROVIDER_RESPONSE") from exc
    if response.status_code == 404:
        raise ProviderError(404, "PROVIDER_RECORD_NOT_FOUND")
    if response.status_code == 409:
        raise ProviderError(409, "QUERY_NOT_OPEN")
    raise ProviderError(502, "PROVIDER_ANSWER_UNCONFIRMED")
