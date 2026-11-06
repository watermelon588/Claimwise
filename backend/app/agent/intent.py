"""Off-plan message handling (DEV-020): I1 classify_intent and R1 reply_off_topic.

Only free text typed by the user is classified. Uploads and button presses are known actions and skip it.
Off-topic messages get a fixed reply naming the current next step; nothing in state changes. When the
classifier fails, the message is treated as a claim question (answered by A1), never as an action.
"""

import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agent.actions import current_step
from app.agent.llm import get_structured_llm
from app.agent.prompts import INTENT_PROMPT, OFF_TOPIC_REPLY
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


class Intent(BaseModel):
    """What the latest user message is about."""

    intent: Literal["claim", "off_topic"]


def classify(text: str) -> str:
    """Model call: 'claim' or 'off_topic'. Any failure counts as 'claim' so a real question is never dropped."""
    try:
        result = get_structured_llm(Intent).invoke([SystemMessage(INTENT_PROMPT), HumanMessage(text[:2000])])
        return result.intent
    except Exception:  # noqa: BLE001 - classifier problems must not block the conversation
        logger.warning("Intent classification failed; treating the message as a claim question", exc_info=True)
        return "claim"


def classify_intent(state: AgentState) -> dict:
    """I1: classify the latest free-text message."""
    return {"intent": classify(state["messages"][-1].text)}


def route_intent(state: AgentState) -> Literal["agent", "reply_off_topic"]:
    """Edge after I1: claim messages go to A1, off-topic ones get the fixed reply."""
    return "reply_off_topic" if state.get("intent") == "off_topic" else "agent"


def reply_off_topic(state: AgentState) -> dict:
    """R1: fixed reply that points back to the current step (the buttons come with the API response)."""
    return {"messages": [AIMessage(OFF_TOPIC_REPLY.format(step=current_step(state)))], "intent": None}
