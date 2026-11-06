"""Onboarding nodes: read uploaded documents (O1), check what is missing (O2), confirm facts (O3).

See docs/diagrams/src/g3-agent-graph.excalidraw for how these connect.
"""

import base64
from datetime import date
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from app.agent.llm import LLMNotConfigured, get_document_llm
from app.agent.prompts import CONFIRM_POLICY_QUESTION, DOCUMENT_EXTRACTION_PROMPT, REJECTED_FILE_REASON
from app.agent.state import AgentState, Document, Policy

POLICY_DOC_TYPES = {"policy_schedule", "e_card", "policy_wording"}
# Types where a second upload is usually a corrected or newer copy: ask "replace or keep both" (DEV-023).
VERSIONED_TYPES = {"discharge_summary", "hospital_bill", "claim_form", "cancelled_cheque", "id_proof", "authority_proof"}


class PolicyFields(BaseModel):
    """Policy facts as printed on the document; None when not printed."""

    insurer: str | None = None
    policy_number: str | None = None
    policy_type: Literal["individual", "family_floater", "group"] | None = None
    members: list[str] = Field(default_factory=list)
    sum_insured: int | None = Field(default=None, description="Whole rupees")
    period_start: str | None = Field(default=None, description="YYYY-MM-DD")
    period_end: str | None = Field(default=None, description="YYYY-MM-DD")
    tpa: str | None = None


EDITABLE_FIELDS = set(PolicyFields.model_fields)

DocType = Literal[
    "policy_schedule", "e_card", "policy_wording", "discharge_summary", "hospital_bill", "pharmacy_bill",
    "investigation_report", "prescription", "insurer_letter", "bank_statement", "id_proof",
    "cancelled_cheque", "claim_form", "authority_proof", "other",
]


class LineItem(BaseModel):
    """One bill line: head (e.g. room rent) and amount in whole rupees."""

    head: str
    amount: int


class HospitalFields(BaseModel):
    """Facts from a discharge summary, bill, pharmacy bill, report or prescription."""

    hospital_name: str | None = None
    patient_name: str | None = None
    admission_date: str | None = Field(default=None, description="YYYY-MM-DD")
    discharge_date: str | None = Field(default=None, description="YYYY-MM-DD")
    diagnosis: str | None = None
    total_amount: int | None = Field(default=None, description="Bill total in whole rupees")
    line_items: list[LineItem] = Field(default_factory=list)


class LineDecision(BaseModel):
    """One line of an insurer decision: claimed vs approved and the stated reason and clause."""

    head: str
    claimed: int | None = None
    approved: int | None = None
    reason: str | None = None
    clause: str | None = Field(default=None, description="Policy clause cited, exactly as printed")


class RequestedDocument(BaseModel):
    """A document an insurer query asks for: the label as written and the closest doc_type."""

    label: str
    doc_type: DocType


class LetterFields(BaseModel):
    """Facts from an insurer or TPA letter."""

    letter_kind: Literal["query", "decision", "settlement", "grievance_reply", "other"]
    letter_date: str | None = Field(default=None, description="YYYY-MM-DD")
    claim_number: str | None = None
    outcome: Literal["approved", "partially_approved", "rejected"] | None = None
    claimed_amount: int | None = None
    approved_amount: int | None = None
    line_decisions: list[LineDecision] = Field(default_factory=list)
    requested_documents: list[RequestedDocument] = Field(default_factory=list)
    reason: str | None = None
    clause: str | None = None
    paid_amount: int | None = Field(default=None, description="Settlement letters: amount paid, whole rupees")
    utr: str | None = Field(default=None, description="Settlement letters: bank transfer reference (UTR/NEFT ref)")
    paid_on: str | None = Field(default=None, description="Settlement letters: payment date, YYYY-MM-DD")


class BankCredit(BaseModel):
    """One credit (money in) line on a bank statement."""

    date: str = Field(description="YYYY-MM-DD")
    amount: int = Field(description="Whole rupees")
    utr: str | None = None
    narration: str | None = None


class BankFields(BaseModel):
    """Facts from a bank statement: the period it covers and its credit lines only."""

    statement_from: str | None = Field(default=None, description="YYYY-MM-DD")
    statement_to: str | None = Field(default=None, description="YYYY-MM-DD")
    credits: list[BankCredit] = Field(default_factory=list)


class AuthorityFields(BaseModel):
    """Facts from a consent letter, power of attorney or insurer registration of a representative."""

    grantor_name: str | None = Field(default=None, description="Person giving the authority (the patient)")
    representative_name: str | None = Field(default=None, description="Person allowed to act")
    issued_on: str | None = Field(default=None, description="YYYY-MM-DD")
    valid_until: str | None = Field(default=None, description="YYYY-MM-DD")


class DocumentExtraction(BaseModel):
    """What the document model returns for one file."""

    doc_type: DocType
    policy: PolicyFields | None = None
    hospital: HospitalFields | None = None
    letter: LetterFields | None = None
    bank: BankFields | None = None
    authority: AuthorityFields | None = None
    summary: str = ""


def extract_document(doc: Document) -> DocumentExtraction:
    """Send one stored file to Gemini and get typed fields back.

    Args:
        doc: Uploaded document record (path and validated mime type).
    Returns:
        Classification, policy fields (for policy documents) and a summary.
    """
    data = base64.b64encode(Path(doc["path"]).read_bytes()).decode()
    kind = "file" if doc["mime_type"] == "application/pdf" else "image"
    file_block = {"type": kind, "base64": data, "mime_type": doc["mime_type"]}
    llm = get_document_llm(DocumentExtraction)
    return llm.invoke([
        SystemMessage(DOCUMENT_EXTRACTION_PROMPT),
        HumanMessage(content_blocks=[{"type": "text", "text": "Read this file."}, file_block]),
    ])


def parse_new_documents(state: AgentState) -> dict:
    """O1: read every document still in 'uploaded' status. Files that are not claim documents are rejected and deleted.

    Args:
        state: Current graph state.
    Returns:
        Updated document records and new pending policies; {} when nothing is new.
    """
    docs, policies = [], []
    for doc in state.get("documents", []):
        if doc["status"] != "uploaded":
            continue
        try:
            result = extract_document(doc)
        except LLMNotConfigured:
            raise  # configuration problem: surface as 503, do not mark the file failed
        except Exception as exc:  # model or file error: keep going, the agent asks for a new copy
            docs.append({**doc, "status": "failed", "error": str(exc)[:200]})
            continue
        if result.doc_type == "other":
            # Not a claim document (a random photo, an unrelated PDF): do not keep the file or its contents.
            Path(doc["path"]).unlink(missing_ok=True)
            docs.append({**doc, "path": "", "status": "rejected", "doc_type": "other",
                         "error": REJECTED_FILE_REASON, "facts": None})
            continue
        facts = result.letter or result.hospital or result.bank or result.authority  # policies are stored below
        parsed = {**doc, "status": "parsed", "doc_type": result.doc_type, "facts": facts.model_dump() if facts else None}
        docs.append(version_check(parsed, [*state.get("documents", []), *docs]))
        if result.doc_type in POLICY_DOC_TYPES and result.policy:
            policies.append({
                **result.policy.model_dump(), "doc_id": doc["id"], "status": "pending", "corrected_fields": [],
            })
    return {"documents": docs, "policies": policies} if docs else {}


def version_check(doc: dict, known: list[dict]) -> dict:
    """Mark a newly parsed document that may be a new version of an earlier one of the same type (DEV-023).

    The user then chooses "replace" or "keep both" with the buttons; until then a block issue stops the pack.

    Args:
        doc: The document just parsed.
        known: Every document record seen so far (state plus this batch).
    Returns:
        The document, with version 1 or with version_of and version_choice pending.
    """
    earlier = [d for d in known if d["id"] != doc["id"] and d["status"] == "parsed" and d.get("doc_type") == doc["doc_type"]]
    if doc["doc_type"] not in VERSIONED_TYPES or not earlier:
        return {**doc, "version": 1}
    return {**doc, "version": 1, "version_of": earlier[-1]["id"], "version_choice": "pending"}


def same_person(a: str, b: str) -> bool:
    """Loose name match: case-insensitive, either name contained in the other."""
    # ponytail: substring match; use proper name matching if real users hit spelling variants.
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a and b) and (a in b or b in a)


def authority_status(state: AgentState, today: date | None = None) -> str:
    """Caregiver authority: not_needed (the user is the patient or no role yet), missing, active, withdrawn or expired."""
    role = state.get("user_role")
    if not role or role["role"] == "self":
        return "not_needed"
    record = state.get("authority")
    if not record:
        return "missing"
    if record.get("status") == "withdrawn":
        return "withdrawn"
    expires = record.get("expires_on")
    if expires and expires < (today or date.today()).isoformat():
        return "expired"
    return "active"


def missing_items(state: AgentState) -> list[str]:
    """List what onboarding still needs, in the order we ask for it.

    Args:
        state: Current graph state.
    Returns:
        Codes from prompts.MISSING_LABELS; empty when onboarding is complete.
    """
    policies = [p for p in state.get("policies", []) if p["status"] != "rejected"]
    confirmed = [p for p in policies if p["status"] == "confirmed"]
    role = state.get("user_role")
    missing = []
    if not policies:
        missing.append("policy_document")
    elif not confirmed:
        missing.append("policy_confirmation")
    if not role:
        missing.append("role")
    elif confirmed and not any(same_person(role["patient_name"], m) for p in confirmed for m in p["members"]):
        missing.append("patient_on_policy")
    # A caregiver needs a recorded, current authority before any claim work (DEV-025).
    if authority_status(state) in ("missing", "withdrawn", "expired"):
        missing.append("authority")
    return missing


def check_onboarding(state: AgentState) -> dict:
    """O2: deterministic onboarding check, stored so the API and the agent see the same answer."""
    missing = missing_items(state)
    return {"onboarding": {"complete": not missing, "missing": missing}}


def route_after_check(state: AgentState) -> Literal["confirm_facts", "review_claim"]:
    """Edge after O2: pause for confirmation while any policy is pending, else review the claim (C1)."""
    pending = any(p["status"] == "pending" for p in state.get("policies", []))
    return "confirm_facts" if pending else "review_claim"


def correction_error(policy: dict, corrections: dict) -> str | None:
    """Why the user's corrections to a policy card cannot be saved (a wrong type or format), or None when they can.

    Checked at the API before the paused run resumes, so a bad value is refused instead of failing the run.
    """
    fields = {k: v for k, v in (corrections or {}).items() if k in EDITABLE_FIELDS}
    try:
        PolicyFields(**{**{k: policy.get(k) for k in EDITABLE_FIELDS}, **fields})
    except ValidationError as exc:
        names = sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")})
        return "These corrections are not valid: " + ", ".join(names) + ". Use whole rupees and YYYY-MM-DD dates."
    return None


def confirm_facts(state: AgentState) -> dict:
    """O3: pause the graph and ask the user to confirm or correct one pending policy.

    The run stops at interrupt(); POST /api/resume continues it with
    {"approved": bool, "corrections": {field: value}}.

    Args:
        state: Current graph state.
    Returns:
        The policy record set to confirmed (with corrections) or rejected.
    """
    policy = next(p for p in state["policies"] if p["status"] == "pending")
    answer = interrupt({"type": "confirm_policy", "question": CONFIRM_POLICY_QUESTION, "policy": policy})
    if not answer.get("approved"):
        return {"policies": [{**policy, "status": "rejected"}]}
    # Only known policy fields can be corrected; anything else is ignored.
    corrections = {k: v for k, v in (answer.get("corrections") or {}).items() if k in EDITABLE_FIELDS}
    fields = PolicyFields(**{**{k: policy[k] for k in EDITABLE_FIELDS}, **corrections})  # re-validate types
    return {"policies": [{
        **policy, **fields.model_dump(), "status": "confirmed", "corrected_fields": sorted(corrections),
    }]}
