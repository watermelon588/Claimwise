"""HTTP routes: health check and chat with the agent."""

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from app.agent.llm import LLMNotConfigured
from app.config import get_settings
from app.db import ping
from app.schemas import ChatRequest, ChatResponse, HealthResponse

router = APIRouter(prefix="/api")


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
    """Send one message to the agent; state persists per thread_id.

    Sync handler on purpose: FastAPI runs it in a thread pool, and the sync
    Postgres checkpointer avoids psycopg's async limits on Windows event loops.
    """
    config = {"configurable": {"thread_id": body.thread_id}}
    try:
        result = request.app.state.graph.invoke(
            {"messages": [HumanMessage(body.message)]}, config
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(thread_id=body.thread_id, reply=result["messages"][-1].text)
