"""Agent graph definition.

v0.2: tool-calling loop. START -> agent -> (tool call? tools -> agent : END).
See docs/diagrams/src/g3-agent-graph.excalidraw (A1 agent, T1 tools).
"""

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.llm import get_llm
from app.agent.prompts import RESPOND_SYSTEM_PROMPT
from app.agent.state import AgentState
from app.agent.tools import TOOLS


def agent(state: AgentState) -> dict:
    """A1: let the LLM reply or request a tool call.

    Args:
        state: Current graph state.
    Returns:
        State update with the model's message (a reply or tool calls) appended.
    """
    reply = get_llm(TOOLS).invoke([SystemMessage(RESPOND_SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [reply]}


def build_graph(checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with persistence.

    Args:
        checkpointer: Saver that stores state per thread_id.
    Returns:
        A compiled LangGraph runnable.
    """
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS))  # T1: runs requested tools, appends ToolMessages
    graph.add_edge(START, "agent")
    # Conditional: tool calls go to "tools", a plain reply ends the run.
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")  # loop back so the model explains the result
    return graph.compile(checkpointer=checkpointer)
