"""HTTP routes: health, chat, document upload and resuming a paused confirmation.

Handlers are sync on purpose: FastAPI runs them in a thread pool, and the sync
Postgres checkpointer avoids psycopg's async limits on Windows event loops.
"""

import hashlib
import hmac
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command

from app import connector
from app.agent.connector_updates import connector_evidence, email_updates
from app.agent.actions import action_input, next_actions
from app.agent.authority import audit, now_iso, validate_authority, withdrawal
from app.agent.grievance import dispute_view
from app.agent.onboarding import authority_status, correction_error
from app.agent.prompts import AUTHORITY_WITHDRAWN_NOTE, DUPLICATE_FILE
from app.agent.llm import LLMNotConfigured
from app.agent.pack_export import approval_status, pack_email, pack_pdf
from app.agent.claim import build_submission_pack, confirmed_policies, confirmed_policy, submission_blockers
from app.config import get_settings
from app.db import ping
from app.observability import run_config
from app.schemas import (
    THREAD_ID_PATTERN, ActionRequest, AuthorityRequest, ChatRequest, ChatResponse, ClaimTypeRequest, ConnectionRequest,
    HealthResponse, ResumeRequest, ThreadRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
UPLOAD_PREFIX = "I uploaded a file: "

# Allowed upload types: declared content type -> (file extension, magic bytes the file must start with).
ALLOWED_UPLOADS = {
    "application/pdf": (".pdf", (b"%PDF",)),
    "image/png": (".png", (b"\x89PNG",)),
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
}


def extract_chunk_text(chunk) -> str:
    """Extract plain text string from an AIMessageChunk or content object."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


# ponytail: per-process locks; one thread never runs twice at once (a user turn and a webhook refresh).
# Several API processes would need a database advisory lock instead.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def thread_lock(thread_id: str) -> threading.Lock:
    """The lock that serialises graph runs and state writes for one thread."""
    with _locks_guard:
        return _locks.setdefault(thread_id, threading.Lock())


def history(values: dict) -> list[dict]:
    """Visible conversation: user text, uploads and button presses, and agent replies (no tool traffic)."""
    out = []
    for msg in values.get("messages") or []:
        if isinstance(msg, HumanMessage):
            text = msg.text
            if msg.name == "upload":
                text = "Uploaded " + text.removeprefix(UPLOAD_PREFIX)
            out.append({"role": "user", "text": text})
        elif isinstance(msg, AIMessage) and msg.text and not msg.tool_calls:
            out.append({"role": "agent", "text": msg.text})
    return out


def shape(request: Request, thread_id: str, values: dict, interrupts, with_history: bool = False) -> dict:
    """The API view of one thread: reply, pending card, reviews, documents, buttons and notices.

    Server file paths are removed from documents. Connector case ids never leave the server.
    Also remembers which thread owns a submitted claim, so the payer webhook can find it.
    """
    last = values["messages"][-1] if values.get("messages") else None
    pending = interrupts[0].value if interrupts else None
    sub, conn = values.get("submission"), values.get("connection")
    if sub and sub.get("claim_id"):
        request.app.state.claim_threads[sub["claim_id"]] = thread_id
    return {
        "thread_id": thread_id,
        "reply": "" if interrupts or not isinstance(last, AIMessage) else last.text,
        "pending": pending,
        "onboarding": values.get("onboarding"),
        "claim": values.get("claim"),
        "documents": [{k: v for k, v in d.items() if k != "path"} for d in values.get("documents") or []],
        "actions": [] if pending else next_actions(values),
        "notifications": sorted(values.get("notifications") or [], key=lambda n: n["at"], reverse=True),
        "submission": {k: v for k, v in sub.items() if k != "client_reference"} if sub else None,
        "connection": {"status": conn["status"], "linked_at": conn["linked_at"]} if conn else None,
        "history": history(values) if with_history else None,
        "answers": {
            **({"members": [m for p in (values.get("policies") or []) if p.get("status") == "confirmed" for m in (p.get("members") or [])]} if any(p.get("status") == "confirmed" for p in (values.get("policies") or [])) else {}),
            **({"claimType": (values.get("claim_info") or {}).get("claim_type")} if (values.get("claim_info") or {}).get("claim_type") else {}),
            **({"patientName": (values.get("user_role") or {}).get("patient_name")} if (values.get("user_role") or {}).get("patient_name") else {}),
        },
        "authority": {**values["authority"], "status": authority_status(values)} if values.get("authority") else None,
        "audit": sorted(values.get("audit") or [], key=lambda a: a["at"], reverse=True)[:50],
        "household": household(values),
        "dispute": dispute_view(values) if values.get("claim") else None,
    }


def household(values: dict) -> dict | None:
    """Confirmed policies, the one this claim goes to, the round and earlier rounds; None before any policy."""
    policies = confirmed_policies(values)
    if not policies:
        return None
    info = values.get("claim_info") or {}
    return {
        "policies": [{k: p.get(k) for k in ("doc_id", "insurer", "policy_number", "policy_type", "members")}
                     for p in policies],
        "chosen": (confirmed_policy(values) or {}).get("doc_id"), "round": info.get("round") or 1,
        "balance_of": info.get("balance_of") or None, "history": values.get("claims_history") or [],
    }


def run_graph(request: Request, thread_id: str, graph_input, route: str) -> ChatResponse:
    """Invoke the agent graph for one thread and shape the API response.

    Args:
        request: Incoming request (holds the compiled graph).
        thread_id: Conversation id; selects the saved state.
        graph_input: New state input, or a Command(resume=...) for a paused run.
        route: Which API route started the run (for tracing).
    Returns:
        ChatResponse with the reply, any pending confirmation, reviews, buttons and notices.
    Raises:
        HTTPException 503: no LLM key configured.
        HTTPException 500: unexpected graph or checkpointer failure (returned as JSON).
    """
    try:
        with thread_lock(thread_id):
            result = request.app.state.graph.invoke(graph_input, run_config(thread_id, route))
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Graph execution failed on thread %s", thread_id)
        raise HTTPException(
            status_code=500,
            detail=f"Server error while processing request ({exc.__class__.__name__}). Please try again.",
        ) from exc
    return ChatResponse(**shape(request, thread_id, result, result.get("__interrupt__") or []))


def refresh(request: Request, thread_id: str) -> dict:
    """Bring a thread up to date without the model: M1 sync, reviews and reminders (check on open).

    Runs only when the thread is at rest (nothing paused or half-run); otherwise returns state as saved.
    The empty input starts a normal run that ends after the review, because the last message is
    already the agent's reply (see actions.route_turn).
    """
    graph, config = request.app.state.graph, {"configurable": {"thread_id": thread_id}}
    with thread_lock(thread_id):
        snapshot = graph.get_state(config)
        if snapshot.values and not snapshot.next and not snapshot.interrupts:
            graph.invoke({"requested_action": None}, run_config(thread_id, "refresh"))
            snapshot = graph.get_state(config)
    values = snapshot.values or {}
    email_updates(values)
    return shape(request, thread_id, values, snapshot.interrupts, with_history=True)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report API, database and LLM provider status."""
    return HealthResponse(
        status="ok",
        database=ping(request.app.state.db_pool),
        llm_provider=get_settings().llm_provider,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """Send one message to the agent; state persists per thread_id."""
    return run_graph(request, body.thread_id, {"messages": [HumanMessage(body.message)]}, "chat")


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, request: Request):
    """Stream agent reply tokens using Server-Sent Events (SSE).

    Yields 'activity' for tool boundaries, 'token' during generation, and
    a final 'done' with updated claim, pending confirmation and onboarding.
    """
    config = {"configurable": {"thread_id": body.thread_id}}
    graph = request.app.state.graph

    def event_stream():
        """Project graph events to public SSE frames without exposing task payloads."""
        lock = thread_lock(body.thread_id)
        lock.acquire()
        try:
            for mode, event in graph.stream(
                {"messages": [HumanMessage(body.message)]},
                run_config(body.thread_id, "stream"),
                stream_mode=["messages", "tasks"],
            ):
                if mode == "tasks":
                    # Only expose whether the tool node is running. Its inputs and outputs stay private.
                    if event["name"] == "tools":
                        state = "tool" if "input" in event else "thinking"
                        yield f"data: {json.dumps({'type': 'activity', 'state': state})}\n\n"
                    continue
                msg, _ = event
                if isinstance(msg, AIMessageChunk):
                    if getattr(msg, "tool_call_chunks", None):
                        continue
                    txt = extract_chunk_text(msg)
                    if txt:
                        yield f"data: {json.dumps({'type': 'token', 'content': txt})}\n\n"

            snapshot = graph.get_state(config)
            payload = {"type": "done", **shape(request, body.thread_id, snapshot.values or {}, snapshot.interrupts)}
            yield f"data: {json.dumps(payload)}\n\n"
        except LLMNotConfigured as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        except Exception as exc:
            logger.exception("Stream execution failed on thread %s", body.thread_id)
            yield f"data: {json.dumps({'type': 'error', 'error': f'Server error ({exc.__class__.__name__}): {exc}'})}\n\n"
        finally:
            lock.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/documents", response_model=ChatResponse)
def upload_document(request: Request, thread_id: str = Form(...), file: UploadFile = File(...)) -> ChatResponse:
    """Save one uploaded file for a thread and let the agent read it (O1).

    Args:
        thread_id: Conversation the file belongs to.
        file: PDF, PNG or JPEG up to max_upload_mb.
    Returns:
        The agent's turn result (often a pending confirmation of policy facts).
    Raises:
        HTTPException 422 for a bad thread id, 415 for a wrong type, 413 when too large.
    """
    if not re.fullmatch(THREAD_ID_PATTERN, thread_id):
        raise HTTPException(status_code=422, detail="Invalid thread_id")
    allowed = ALLOWED_UPLOADS.get(file.content_type or "")
    settings = get_settings()
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    # Check the real bytes too: the declared content type comes from the client.
    if not allowed or not data.startswith(allowed[1]):
        raise HTTPException(status_code=415, detail="Upload a PDF, PNG or JPEG file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB")
    # DEV-023: the exact same bytes again add nothing (a corrected file has different bytes and is versioned by O1).
    sha256 = hashlib.sha256(data).hexdigest()
    same = next((d for d in snapshot_of(request, thread_id).values.get("documents") or []
                 if d.get("sha256") == sha256 and d["status"] != "rejected"), None)
    if same:
        raise HTTPException(status_code=409, detail=DUPLICATE_FILE.format(
            filename=same["filename"], date=(same.get("uploaded_at") or "earlier")[:10]))

    doc_id = uuid.uuid4().hex
    path = Path(settings.upload_dir) / thread_id / f"{doc_id}{allowed[0]}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    filename = Path(file.filename or "upload").name[:200]
    doc = {
        "id": doc_id, "filename": filename, "mime_type": file.content_type, "path": str(path),
        "status": "uploaded", "doc_type": None, "error": None, "facts": None, "sha256": sha256,
        "uploaded_at": now_iso(),
    }
    return run_graph(request, thread_id, {
        "documents": [doc], "messages": [HumanMessage(UPLOAD_PREFIX + filename, name="upload")],
    }, "upload")


@router.post("/resume", response_model=ChatResponse)
def resume(body: ResumeRequest, request: Request) -> ChatResponse:
    """Answer a paused confirmation (O3 policy facts or the submission pack approval) and continue the run.

    Raises:
        HTTPException 409: the thread has nothing waiting for an answer.
    """
    try:
        snapshot = request.app.state.graph.get_state({"configurable": {"thread_id": body.thread_id}})
    except Exception as exc:
        logger.exception("Failed reading state on thread %s", body.thread_id)
        raise HTTPException(
            status_code=500,
            detail=f"Database connection error while reading thread state ({exc.__class__.__name__}). Please try again.",
        ) from exc
    if not snapshot.interrupts:
        raise HTTPException(status_code=409, detail="Nothing is waiting for confirmation on this thread")
    card = snapshot.interrupts[0].value or {}
    # Validate policy corrections here, at the trust boundary, so a bad value never reaches the paused run.
    error = correction_error(card["policy"], body.corrections) if card.get("type") == "confirm_policy" and body.approved else None
    if error:
        raise HTTPException(status_code=422, detail=error)
    answer = {"approved": body.approved, "corrections": body.corrections}
    return run_graph(request, body.thread_id, Command(resume=answer), "resume")


def checked_thread(thread_id: str) -> str:
    """Validate a thread id taken from the URL path (it also names the upload folder)."""
    if not re.fullmatch(THREAD_ID_PATTERN, thread_id):
        raise HTTPException(status_code=422, detail="Invalid thread_id")
    return thread_id


def snapshot_of(request: Request, thread_id: str):
    """Saved state of one thread; 500 as JSON when the database cannot be read."""
    try:
        return request.app.state.graph.get_state({"configurable": {"thread_id": thread_id}})
    except Exception as exc:
        logger.exception("Failed reading state on thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Could not read the saved claim. Please try again.") from exc


def write_state(request: Request, thread_id: str, update: dict) -> None:
    """Apply a small state change outside a run (connection, notifications) while the thread is at rest.

    as_node is R1, whose only edge is END, so no step is left pending and the next run starts normally.
    """
    graph, config = request.app.state.graph, {"configurable": {"thread_id": thread_id}}
    with thread_lock(thread_id):
        if graph.get_state(config).interrupts:
            raise HTTPException(status_code=409, detail="Answer the card on screen first.")
        graph.update_state(config, update, as_node="reply_off_topic")


@router.get("/threads")
def list_threads(request: Request, ids: str = "") -> list[dict]:
    """Summaries for the history sidebar, only for the thread ids this browser already holds.

    There is no user login yet (TBD), so the server never lists every claim in the database: a thread id is
    the only key to a claim, and only its holder can ask for it.

    Args:
        ids: Comma-separated thread ids (at most 25); invalid ids are skipped.
    """
    graph = request.app.state.graph
    thread_ids = [t for t in dict.fromkeys(ids.split(","))
                  if re.fullmatch(THREAD_ID_PATTERN, t)][:25]
    summaries = []
    for tid in thread_ids:
        try:
            snap = graph.get_state({"configurable": {"thread_id": tid}})
            vals = snap.values or {}
            if not vals:
                continue
            docs = [d for d in (vals.get("documents") or []) if d.get("status") != "rejected"]
            policies = [p for p in (vals.get("policies") or []) if p.get("status") != "rejected"]
            role = vals.get("user_role") or {}
            claim = vals.get("claim") or {}
            onboarding = vals.get("onboarding") or {}
            vis_msgs = history(vals)
            # Build a meaningful human title for the thread
            patient = role.get("patient_name")
            pol_num = policies[0].get("policy_number") if policies else None
            insurer = policies[0].get("insurer") if policies else None
            if patient and pol_num:
                title = f"{patient} · {pol_num}"
            elif pol_num:
                title = f"{insurer or 'Policy'} ({pol_num})"
            elif docs:
                title = docs[0].get("filename") or f"Claim {tid[:8]}"
            elif vis_msgs:
                title = vis_msgs[0]["text"][:42]
            else:
                title = f"Claim {tid[:8]}"
            summaries.append({
                "thread_id": tid,
                "title": title,
                "stage": claim.get("stage") if onboarding.get("complete") else "onboarding",
                "onboarding_complete": bool(onboarding.get("complete")),
                "doc_count": len(docs),
                "message_count": len(vis_msgs),
                "claim_type": (vals.get("claim_info") or {}).get("claim_type"),
            })
        except Exception:
            continue
    return summaries


@router.get("/thread/{thread_id}", response_model=ChatResponse)
def get_thread(thread_id: str, request: Request) -> ChatResponse:
    """Reopen a claim: check the insurer for updates and raise reminders, then return state and conversation."""
    checked_thread(thread_id)
    try:
        return ChatResponse(**refresh(request, thread_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Refresh failed on thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Could not load the saved claim. Please try again.") from exc


@router.post("/action", response_model=ChatResponse)
def press_action(body: ActionRequest, request: Request) -> ChatResponse:
    """Run a next-step button. Only buttons offered for the current state are accepted.

    Raises:
        HTTPException 409: a card is waiting for an answer, or the button is not offered now.
        HTTPException 422: the button is handled in the browser (upload, download, connect).
    """
    snapshot = snapshot_of(request, body.thread_id)
    if snapshot.interrupts:
        raise HTTPException(status_code=409, detail="Answer the card on screen first.")
    offered = [a for a in next_actions(snapshot.values or {}) if a["id"] == body.action]
    # A button that carries its own data (which document, which policy) must be pressed with exactly that data.
    fixed = [a["data"] for a in offered if "data" in a]
    if not offered or (fixed and body.data not in fixed):
        raise HTTPException(status_code=409, detail="That step is not available right now. Use the buttons on screen.")
    graph_input = action_input(body.action, body.data)
    if graph_input is None:
        raise HTTPException(status_code=422, detail="This button works in the browser.")
    return run_graph(request, body.thread_id, graph_input, f"action:{body.action}")


@router.post("/connection", response_model=ChatResponse)
def link_connection(body: ConnectionRequest, request: Request) -> ChatResponse:
    """Bind a connected insurer account to this claim, using the code shown on the connector page. Mock only.

    The TPA must be connected there, because that consent covers submission and status reads.
    """
    try:
        tools = connector.connected_tools(body.code)
    except connector.ConnectorError as exc:
        if exc.code == "NOT_CONFIGURED":
            raise HTTPException(status_code=503, detail="Insurer connections are not enabled on this server.") from exc
        if exc.status == 0:
            raise HTTPException(status_code=503, detail="The connector page is not reachable. Try again.") from exc
        raise HTTPException(status_code=400, detail="That code is not valid or has expired. Open the connector page again.") from exc
    if "read_claim" not in tools:
        raise HTTPException(status_code=400, detail="Connect Medivista TPA on the connector page first. It allows submission.")
    linked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    write_state(request, body.thread_id, {"connection": {"case_id": body.code, "linked_at": linked_at, "status": "active"}})
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/connection/sync", response_model=ChatResponse)
def sync_workspace_connections(body: ConnectionRequest, request: Request) -> ChatResponse:
    """Bind the verified gateway workspace and read only the scopes approved for this thread."""
    graph, config = request.app.state.graph, {"configurable": {"thread_id": body.thread_id}}
    with thread_lock(body.thread_id):
        snapshot = graph.get_state(config)
        values = snapshot.values or {}
        if not (values.get("onboarding") or {}).get("complete") or snapshot.next or snapshot.interrupts:
            raise HTTPException(409, "Finish the current step before connecting tools.")
        try:
            tools = connector.connected_tools(body.code, body.thread_id)
        except connector.ConnectorError as exc:
            if exc.status in (401, 403):
                workspace = values.get("workspace_connectors") or {}
                if exc.status == 401 and workspace.get("case_id") == body.code:
                    update = {"workspace_connectors": {}}
                    if (values.get("connection") or {}).get("case_id") == body.code:
                        update["connection"] = None
                    graph.update_state(config, update, as_node="reply_off_topic")
                raise HTTPException(403, "Verify this demo workspace before connecting tools.") from exc
            raise HTTPException(503, "The demo connector service is unavailable.") from exc

        at = datetime.now(timezone.utc).isoformat()
        previous = values.get("workspace_connectors") or {}
        evidence, notices = connector_evidence(body.code, tools, previous, values, at)
        update = {"workspace_connectors": {"case_id": body.code, "tools": tools, "evidence": evidence}}
        if notices:
            update["notifications"] = notices
        tpa = values.get("connection") or {}
        if "read_claim" in tools and (not tpa or tpa["case_id"] == body.code or tpa.get("status") != "active"):
            update["connection"] = {**tpa, "case_id": body.code, "linked_at": tpa.get("linked_at", at), "status": "active"}
        elif tpa.get("case_id") == body.code and "read_claim" not in tools:
            update["connection"] = None
        graph.update_state(config, update, as_node="reply_off_topic")
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/connection/remove", response_model=ChatResponse)
def unlink_connection(body: ThreadRequest, request: Request) -> ChatResponse:
    """Forget the connected account for this claim. Consent itself is revoked on the connector page."""
    write_state(request, body.thread_id, {"connection": None})
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/claim-type", response_model=ChatResponse)
def set_claim_type(body: ClaimTypeRequest, request: Request) -> ChatResponse:
    """Record cashless or reimbursement from the buttons, without relying on the model to call a tool.

    A change before submission makes any pack approval stale (C1 flags it); after submission it is refused.

    Raises:
        HTTPException 409: the claim was already submitted with another type.
    """
    values = snapshot_of(request, body.thread_id).values or {}
    info = values.get("claim_info") or {}
    if info.get("submitted_on") and info.get("claim_type") not in (None, body.claim_type):
        raise HTTPException(status_code=409, detail=f"The claim was already submitted as {info['claim_type']}.")
    write_state(request, body.thread_id, {"claim_info": {"claim_type": body.claim_type},
                                          "audit": [audit(values, "set_claim_type", f"Claim type: {body.claim_type}")]})
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/authority", response_model=ChatResponse)
def record_authority(body: AuthorityRequest, request: Request) -> ChatResponse:
    """Record a caregiver's authority to act for the patient, checked against the uploaded proof (DEV-025).

    Claimwise records authority; the insurer decides whether it accepts the representative.

    Raises:
        HTTPException 422: the form does not match the role or the proof (reason in plain words).
    """
    values = snapshot_of(request, body.thread_id).values or {}
    record, error = validate_authority(values, body.model_dump())
    if error:
        raise HTTPException(status_code=422, detail=error)
    entry = audit({**values, "authority": record}, "record_authority",
                  f"{record['basis']}, covers {', '.join(record['scope'])}, expires {record['expires_on'] or 'never'}")
    write_state(request, body.thread_id, {"authority": record, "audit": [entry]})
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/authority/withdraw", response_model=ChatResponse)
def withdraw_authority(body: ThreadRequest, request: Request) -> ChatResponse:
    """Record that the patient withdrew consent: work pauses and any pack approval is cancelled (DEV-025).

    Raises:
        HTTPException 409: there is no active authority on this claim.
    """
    values = snapshot_of(request, body.thread_id).values or {}
    if authority_status(values) != "active":
        raise HTTPException(status_code=409, detail="There is no active authority to withdraw.")
    patient = (values.get("user_role") or {}).get("patient_name") or "the patient"
    note = {"id": f"note-withdrawn-{uuid.uuid4().hex[:8]}", "at": now_iso(), "kind": "warning",
            "text": AUTHORITY_WITHDRAWN_NOTE.format(patient=patient), "read": False}
    write_state(request, body.thread_id, {**withdrawal(values), "notifications": [note],
                                          "audit": [audit(values, "withdraw_authority", note["text"])]})
    return ChatResponse(**refresh(request, body.thread_id))


@router.post("/notifications/read", response_model=ChatResponse)
def read_notifications(body: ThreadRequest, request: Request) -> ChatResponse:
    """Mark every notification on this claim as read."""
    notes = snapshot_of(request, body.thread_id).values.get("notifications") or []
    if any(not n["read"] for n in notes):
        write_state(request, body.thread_id, {"notifications": [{**n, "read": True} for n in notes]})
    return ChatResponse(**refresh(request, body.thread_id))


def ready_pack_state(request: Request, thread_id: str) -> dict:
    """State of a thread whose claim pack can be built (onboarded, no blockers), else 409 with the reasons."""
    values = snapshot_of(request, checked_thread(thread_id)).values or {}
    blockers = submission_blockers(values) if values else ["no claim on this thread yet"]
    if blockers:
        raise HTTPException(status_code=409, detail="The claim pack is not ready: " + "; ".join(blockers))
    return values


@router.get("/pack/{thread_id}")
def get_pack(thread_id: str, request: Request, response: Response) -> dict:
    """The current claim pack (cover letter and documents) and whether this exact pack is approved."""
    values = ready_pack_state(request, thread_id)
    pack = build_submission_pack(values)
    response.headers["Cache-Control"] = "no-store"
    return {"pack": pack, "status": approval_status(values, pack),
            "approved_at": (values.get("submission_approval") or {}).get("approved_at")}


@router.get("/pack/{thread_id}/documents/{document_id}")
def view_pack_document(thread_id: str, document_id: str, request: Request) -> FileResponse:
    """Open an original only when it belongs to the current pack and thread upload directory."""
    values = ready_pack_state(request, thread_id)
    pack = build_submission_pack(values)
    included = any(doc["id"] == document_id for doc in pack["documents"])
    document = next((doc for doc in values.get("documents", []) if doc["id"] == document_id), None) if included else None
    if not document or not document.get("path") or document.get("mime_type") not in ALLOWED_UPLOADS:
        raise HTTPException(status_code=404, detail="That original is not available in this claim pack.")
    path = Path(document["path"]).resolve()
    folder = (Path(get_settings().upload_dir) / thread_id).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(status_code=404, detail="That original is not available in this claim pack.")
    return FileResponse(
        path, media_type=document["mime_type"], filename=document["filename"], content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/pack/{thread_id}/pdf")
def download_pack_pdf(thread_id: str, request: Request) -> Response:
    """The claim pack as one PDF: cover letter, then every document in pack order."""
    data, pack = pack_pdf(ready_pack_state(request, thread_id))
    return Response(data, media_type="application/pdf",
                    headers={"Cache-Control": "no-store",
                             "Content-Disposition": f'attachment; filename="claim-pack-{pack["hash"]}.pdf"'})


@router.get("/pack/{thread_id}/eml")
def download_pack_email(thread_id: str, request: Request) -> Response:
    """The claim pack as an unsent email draft with the documents attached (recipient left empty)."""
    data, pack = pack_email(ready_pack_state(request, thread_id))
    return Response(data, media_type="message/rfc822",
                    headers={"Cache-Control": "no-store",
                             "Content-Disposition": f'attachment; filename="claim-pack-{pack["hash"]}.eml"'})


@router.post("/webhooks/mock", status_code=202)
async def mock_webhook(request: Request) -> dict:
    """Signed status event from the mock payer: refresh the thread that owns the claim.

    The signature (HMAC SHA-256 over the raw body) is checked first. Duplicates are harmless because the
    refresh is idempotent. Unknown claims are ignored; the next check on open catches up.
    """
    secret = get_settings().mock_webhook_secret
    if not secret:
        raise HTTPException(status_code=404, detail="Not found")
    raw = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("x-mock-signature", ""), expected):
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        event = json.loads(raw)
        claim_id = event["resource"]["id"] if event["resource"]["type"] == "claim" else None
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Bad event") from exc
    thread_id = request.app.state.claim_threads.get(claim_id)
    if not thread_id:
        return {"status": "ignored"}
    await run_in_threadpool(refresh, request, thread_id)
    return {"status": "refreshed"}
