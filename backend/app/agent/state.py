"""Agent state shared by all graph nodes.

Placeholder: only the message history for now. Claim, policy, request and
payment fields are added when the agent graph is designed.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State carried through the graph and saved at every checkpoint.

    Attributes:
        messages: Conversation history; add_messages appends instead of overwriting.
    """

    messages: Annotated[list[AnyMessage], add_messages]
