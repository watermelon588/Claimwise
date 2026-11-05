"""Agent graph definition.

v0.6: connector sync, onboarding, claim review, payment check, then buttons, intent check or the agent.
START -> M1 sync_connector -> O1 parse_new_documents -> O2 check_onboarding -> (O3 confirm_facts pause | C1 review_claim)
C1 -> (P1 verify_payment, once the insurer decided or says it paid | turn route); P1 -> turn route.
Turn route: a pressed button -> X1 run_action -> C1 (refresh) -> END; typed text -> I1 classify_intent ->
(A1 agent | R1 reply_off_topic -> END); uploads, button instructions and tool results -> A1.
A1 -> (T1 tools -> O2 | END). Pack approval pauses inside T1 (prepare_submission) or X1 (Prepare button).
See docs/diagrams/src/g3-agent-graph.excalidraw.
"""

import json
from datetime import date

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.actions import next_actions, route_turn, run_action
from app.agent.claim import confirmed_policies, confirmed_policy, review_claim
from app.agent.grievance import dispute_view
from app.agent.intent import classify_intent, reply_off_topic, route_intent
from app.agent.llm import get_llm
from app.agent.monitor import reminders, sync_connector
from app.agent.onboarding import authority_status, check_onboarding, confirm_facts, parse_new_documents, route_after_check
from app.agent.payment import route_after_review, verify_payment
from app.agent.prompts import (
    CLAIM_CONTEXT_TEMPLATE, DOC_TYPE_LABELS, MISSING_LABELS, NEXT_STEP_RULE, ONBOARDING_CONTEXT_TEMPLATE,
    RESPOND_SYSTEM_PROMPT,
)
from app.agent.state import AgentState
from app.agent.tools import TOOLS


def onboarding_context(state: AgentState) -> str:
    """Render the onboarding snapshot the agent sees every turn.

    Args:
        state: Current graph state (after O2).
    Returns:
        Filled ONBOARDING_CONTEXT_TEMPLATE text.
    """
    onboarding = state.get("onboarding", {"complete": False, "missing": []})
    docs = [f"{d['filename']} ({d['status']}, {d.get('doc_type') or 'unknown'})" for d in state.get("documents", [])]
    policies = [
        {k: p[k] for k in ("insurer", "policy_number", "policy_type", "members", "sum_insured", "period_start", "period_end", "tpa")}
        for p in state.get("policies", []) if p["status"] == "confirmed"
    ]
    return ONBOARDING_CONTEXT_TEMPLATE.format(
        complete=onboarding["complete"],
        missing="; ".join(MISSING_LABELS[m] for m in onboarding["missing"]) or "nothing",
        documents="; ".join(docs) or "none uploaded",
        policies=policies or "none",
        role=state.get("user_role") or "not recorded",
    )


def claim_context(state: AgentState) -> str:
    """Render the C1 claim review the agent sees every turn.

    Args:
        state: Current graph state (after C1, and P1 when it ran).
    Returns:
        Filled CLAIM_CONTEXT_TEMPLATE text; structured parts as compact JSON.
    """
    claim = state.get("claim") or review_claim(state)["claim"]
    checklist = claim["checklist"]
    label = lambda types: ", ".join(DOC_TYPE_LABELS.get(t, t) for t in types) or "none"  # noqa: E731
    return CLAIM_CONTEXT_TEMPLATE.format(
        stage=claim["stage"],
        claim_info=state.get("claim_info") or "none",
        have=", ".join(checklist["have"]) or "none",
        missing_required=label(checklist["missing_required"]),
        missing_recommended=label(checklist["missing_recommended"]),
        issues="; ".join(f"[{i['severity']}] {i['message']}" for i in claim["issues"]) or "none",
        query=json.dumps(claim["query"]) if claim["query"] else "none",
        decision=json.dumps(claim["decision"]) if claim["decision"] else "none",
        payment=json.dumps(claim["payment"]) if claim.get("payment") else "not checked yet (no decision or settlement)",
        submission=json.dumps(state.get("submission")) if state.get("submission") else "not submitted",
        connection=(state.get("connection") or {}).get("status", "no insurer account connected"),
        policies=household(state),
        history=json.dumps(state.get("claims_history")) if state.get("claims_history") else "none",
        authority=authority_text(state),
        dispute=json.dumps(dispute_view(state)) if dispute_view(state) else "none",
    )


def household(state: AgentState) -> str:
    """Confirmed policies and which one this claim goes to, for the agent context."""
    chosen = (confirmed_policy(state) or {}).get("doc_id")
    rows = [f"{p['insurer']} {p['policy_number']} ({p['policy_type'] or 'type not stated'})"
            + (" [this claim]" if p["doc_id"] == chosen else "") for p in confirmed_policies(state)]
    return "; ".join(rows) or "none"


def authority_text(state: AgentState) -> str:
    """Caregiver authority status and scope in one line (no proof file details)."""
    status = authority_status(state)
    record = state.get("authority") or {}
    if status in ("not_needed", "missing"):
        return status.replace("_", " ")
    return f"{status}: {record.get('basis')}, covers {', '.join(record.get('scope') or [])}, expires {record.get('expires_on') or 'never'}"


def agent(state: AgentState) -> dict:
    """A1: reply to the user or request a tool call, guided by the onboarding snapshot.

    Args:
        state: Current graph state.
    Returns:
        State update with the model's message (a reply or tool calls) appended.
    """
    buttons = ", ".join(a["label"] for a in next_actions(state)) or "none (the setup form is on screen)"
    system = [
        SystemMessage(RESPOND_SYSTEM_PROMPT + " " + NEXT_STEP_RULE),
        SystemMessage(onboarding_context(state) + "\n\n" + claim_context(state) + f"\n\nButtons under your reply: {buttons}"),
    ]
    reply = get_llm(TOOLS).invoke([*system, *state["messages"]])
    return {"messages": [reply]}


TURN_TARGETS = ["run_action", "classify_intent", "agent", END]


def after_review(state: AgentState) -> str:
    """Edge after C1: P1 once the insurer decided or says it paid, otherwise the turn route."""
    return "verify_payment" if route_after_review(state) == "verify_payment" else route_turn(state)


def review_and_remind(state: AgentState) -> dict:
    """C1: review the claim, then raise reminders that this turn's uploads made due.

    M1 raises reminders before O1 reads new uploads, so a letter uploaded now (a grievance reply, a revised
    decision) would otherwise wait for the next turn. Reminder ids are fixed, so nothing is raised twice.
    """
    out = review_claim(state)
    notes = reminders({**state, **out}, date.today())
    return {**out, "notifications": notes} if notes else out


def build_graph(checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with persistence.

    Args:
        checkpointer: Saver that stores state per thread_id (also needed for the O3 pause).
    Returns:
        A compiled LangGraph runnable.
    """
    graph = StateGraph(AgentState)
    graph.add_node("sync_connector", sync_connector)  # M1
    graph.add_node("parse_new_documents", parse_new_documents)  # O1
    graph.add_node("check_onboarding", check_onboarding)  # O2
    graph.add_node("confirm_facts", confirm_facts)  # O3
    graph.add_node("review_claim", review_and_remind)  # C1
    graph.add_node("verify_payment", verify_payment)  # P1
    graph.add_node("agent", agent)  # A1
    graph.add_node("tools", ToolNode(TOOLS))  # T1
    graph.add_node("run_action", run_action)  # X1
    graph.add_node("classify_intent", classify_intent)  # I1
    graph.add_node("reply_off_topic", reply_off_topic)  # R1

    graph.add_edge(START, "sync_connector")
    graph.add_edge("sync_connector", "parse_new_documents")
    graph.add_edge("parse_new_documents", "check_onboarding")
    graph.add_conditional_edges("check_onboarding", route_after_check)  # O3 pause or C1
    graph.add_conditional_edges("review_claim", after_review, [*TURN_TARGETS, "verify_payment"])
    graph.add_conditional_edges("verify_payment", route_turn, TURN_TARGETS)
    graph.add_edge("run_action", "review_claim")  # a button changed state: refresh the review, then END
    graph.add_conditional_edges("classify_intent", route_intent)  # A1 or the fixed off-topic reply
    graph.add_edge("reply_off_topic", END)
    graph.add_edge("confirm_facts", "check_onboarding")  # recheck after the user answers
    graph.add_conditional_edges("agent", tools_condition)  # tool call -> tools, reply -> END
    graph.add_edge("tools", "check_onboarding")  # tools change state (role, claim facts, approval): recheck
    return graph.compile(checkpointer=checkpointer)
