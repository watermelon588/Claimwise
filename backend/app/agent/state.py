"""Agent state shared by all graph nodes and saved at every checkpoint (per thread_id).

Lists of records merge by key, so a node can return only the records it changed.
"""

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def merge_by(key: str):
    """Build a reducer that upserts list items by a key field.

    Args:
        key: Field that identifies a record (for example "id").
    Returns:
        Reducer(old, new) -> list where items in new replace same-key items in old, others append.
    """

    def reducer(old: list[dict] | None, new: list[dict] | None) -> list[dict]:
        """Upsert: records in new replace same-key records in old; the rest keep their order."""
        merged = {item[key]: item for item in old or []}
        merged.update({item[key]: item for item in new or []})
        return list(merged.values())

    return reducer


def merge_dict(old: dict | None, new: dict | None) -> dict:
    """Reducer for user-stated facts: new non-None values overwrite, None leaves the old value."""
    return {**(old or {}), **{k: v for k, v in (new or {}).items() if v is not None}}


class Document(TypedDict):
    """One uploaded file.

    Attributes:
        id: Server-generated id (also the stored file name stem).
        filename: Original name from the user, display only.
        mime_type: Validated content type.
        path: Where the file is stored on disk.
        status: uploaded (not read yet), parsed, failed (unreadable), rejected (not a claim document;
            the stored file is deleted and path is empty), superseded (replaced by a newer version), or
            archived (an insurer letter or bank statement from an earlier claim round; kept as evidence).
        doc_type: What the model classified it as, once parsed.
        error: Short reason when parsing failed.
        facts: Fields read from a hospital document or insurer letter (see onboarding.py), else None.
        sha256: Fingerprint of the uploaded bytes; the same file twice is refused at upload.
        uploaded_at: When it was uploaded (ISO time).
        version: 1 for a first document of its type, n+1 when it replaced version n.
        version_of: Earlier document of the same type this one may replace (set by O1).
        version_choice: pending (ask: replace or keep both), replaced, or kept.
        source: connector for records read from a connected account; absent for uploads.
    """

    id: str
    filename: str
    mime_type: str
    path: str
    status: Literal["uploaded", "parsed", "failed", "rejected", "superseded", "archived"]
    doc_type: str | None
    error: str | None
    facts: dict | None
    sha256: NotRequired[str]
    uploaded_at: NotRequired[str]
    version: NotRequired[int]
    version_of: NotRequired[str | None]
    version_choice: NotRequired[Literal["pending", "replaced", "kept"] | None]
    source: NotRequired[str]


class Policy(TypedDict):
    """Policy facts read from one policy document, with provenance and confirmation.

    Attributes:
        doc_id: Document the facts came from.
        status: pending (read, not yet checked by the user), confirmed, or rejected.
        corrected_fields: Fields the user changed during confirmation.
        Other keys: the extracted fields (insurer, policy_number, policy_type, members,
        sum_insured, period_start, period_end, tpa); any may be None if not found.
    """

    doc_id: str
    status: Literal["pending", "confirmed", "rejected"]
    corrected_fields: list[str]
    insurer: str | None
    policy_number: str | None
    policy_type: str | None
    members: list[str]
    sum_insured: int | None
    period_start: str | None
    period_end: str | None
    tpa: str | None


class UserRole(TypedDict):
    """Who is using Claimwise and for whom."""

    role: Literal["self", "caregiver"]
    patient_name: str
    relation: str


class Onboarding(TypedDict):
    """Result of the onboarding check (O2)."""

    complete: bool
    missing: list[str]


class ClaimInfo(TypedDict, total=False):
    """Claim facts the user states or chooses (not found in documents).

    Attributes:
        policy_doc_id: The policy the claimant chose to claim on (with several policies).
        round: 1 for the first claim; 2 and up for a balance claim on another policy.
        balance_of: For a balance claim, what the earlier insurer decided ({insurer, claim_number, claimed,
            approved, balance}).
        submitted_on, claim_number: Empty strings (not None) after a new round starts, because None is
            ignored by the merge.
    """

    claim_type: Literal["cashless", "reimbursement"]
    submitted_on: str
    claim_number: str
    policy_doc_id: str
    round: int
    balance_of: dict


class SubmissionApproval(TypedDict):
    """The user's approval of one exact submission pack (by content hash)."""

    hash: str
    approved_at: str


class Connection(TypedDict):
    """An insurer or TPA account the user connected on the connector page, bound to this claim thread.

    Mock only: the case id is the code shown on the gateway page. There is no real user login yet.
    """

    case_id: str
    linked_at: str
    status: Literal["active", "expired"]


class Submission(TypedDict, total=False):
    """How the approved pack reached the insurer, and what monitoring last saw.

    Attributes:
        route: connector (Claimwise submitted it) or manual (the user did).
        pack_hash: The approved pack that was submitted.
        client_reference: Our reference for the claim at the payer; also the idempotency key.
        status: unconfirmed (sent, answer lost: look up before retrying), submitted, or refused.
        claim_id: The payer's claim number once known.
        error: Short reason for refused or unconfirmed.
        last_checked: When monitoring last read the claim (ISO time).
    """

    route: Literal["connector", "manual"]
    pack_hash: str
    client_reference: str
    status: Literal["unconfirmed", "submitted", "refused"]
    claim_id: str | None
    submitted_at: str | None
    error: str | None
    last_checked: str | None


class Authority(TypedDict, total=False):
    """A caregiver's authority to act for the patient (DEV-025). Claimwise records it; it cannot grant it.

    Attributes:
        representative_name: The caregiver's own name, as registered with the insurer.
        basis: policyholder, insurer_registration, power_of_attorney or patient_consent.
        proof_doc_id: Uploaded proof (not needed when the caregiver is the policyholder).
        scope: What it covers: submit_claim, share_records, receive_updates, file_grievance.
        expires_on: Last valid day, or None when it does not expire.
        status: active or withdrawn.
    """

    representative_name: str
    basis: Literal["policyholder", "insurer_registration", "power_of_attorney", "patient_consent"]
    proof_doc_id: str | None
    scope: list[str]
    expires_on: str | None
    status: Literal["active", "withdrawn"]
    recorded_at: str
    withdrawn_at: str | None


class AuditEntry(TypedDict):
    """One line of the audit log: who did what and when (DEV-025)."""

    id: str
    at: str
    actor: str
    action: str
    detail: str


class Dispute(TypedDict, total=False):
    """What the user did to dispute a decision (DEV-026). Status is derived in grievance.dispute_view().

    Attributes:
        decision_doc_id: The decision letter being disputed.
        grievance_hash, grievance_approved_at: The grievance letter the user approved.
        grievance_filed_on, grievance_ref: When and with what reference the user sent it.
        ombudsman_hash, ombudsman_approved_at, ombudsman_filed_on, ombudsman_ref: Same for the Ombudsman.
    """

    decision_doc_id: str
    grievance_hash: str
    grievance_approved_at: str
    grievance_filed_on: str
    grievance_ref: str
    ombudsman_hash: str
    ombudsman_approved_at: str
    ombudsman_filed_on: str
    ombudsman_ref: str


class Notification(TypedDict):
    """One in-app notice: an insurer update, a reminder, or a warning. Ids are deterministic, so no duplicates.

    resolved: a reminder whose condition passed (kept for history, no longer asks the user to act).
    """

    id: str
    at: str
    kind: Literal["update", "reminder", "warning"]
    text: str
    read: bool
    resolved: NotRequired[bool]


class AgentState(TypedDict, total=False):
    """State carried through the graph.

    Attributes:
        messages: Conversation history; add_messages appends.
        documents: Uploaded files, upserted by id. Records read from a connector have source "connector".
        policies: Policy facts per document, upserted by doc_id.
        user_role: Self or caregiver, and the patient; None until recorded.
        onboarding: What is still missing before claim work can start.
        claim_info: User-stated claim facts, merged field by field.
        submission_approval: Approved pack hash; stale when the pack changes.
        claim: Review computed by C1 every turn (stage, checklist, issues, decision, query).
        connection: Connected insurer or TPA account for this claim, or None.
        submission: Submission route and status, or None before submission.
        notifications: In-app notices, upserted by id.
        requested_action: A button the user pressed that runs without the model ({id, data}); cleared after.
        intent: Classification of the latest free-text message (claim, off_topic); set by I1.
        authority: Caregiver authority record, or None (not needed when the user is the patient).
        audit: Who did what, upserted by id.
        dispute: Grievance and Ombudsman steps the user took, or None.
        claims_history: Earlier claim rounds (one per policy claimed), newest last.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    documents: Annotated[list[Document], merge_by("id")]
    policies: Annotated[list[Policy], merge_by("doc_id")]
    user_role: UserRole | None
    onboarding: Onboarding
    claim_info: Annotated[ClaimInfo, merge_dict]
    submission_approval: SubmissionApproval | None
    claim: dict
    connection: Connection | None
    submission: Submission | None
    notifications: Annotated[list[Notification], merge_by("id")]
    requested_action: dict | None
    intent: str | None
    authority: Authority | None
    audit: Annotated[list[AuditEntry], merge_by("id")]
    dispute: Annotated[Dispute, merge_dict]
    claims_history: list[dict]
