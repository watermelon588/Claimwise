"""FastAPI entry point: builds the agent graph at startup and mounts the routes.

Run from backend/: uv run uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_graph
from app.api.routes import router
from app.config import get_settings
from app.db import open_checkpointer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the checkpointer and compile the graph once; close the DB pool on shutdown."""
    saver, pool = open_checkpointer()
    app.state.db_pool = pool
    app.state.graph = build_graph(saver)
    yield
    if pool is not None:
        pool.close()


app = FastAPI(title="Claimwise API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
