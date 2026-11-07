"""Database connection and LangGraph checkpointer setup.

Neon Postgres stores LangGraph checkpoints, so every conversation thread survives
a server restart. Without DATABASE_URL the app falls back to an in-memory saver
so it can run before the database is provisioned.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.config import get_settings


def delete_checkpoints(saver: BaseCheckpointSaver, thread_id: str) -> None:
    """Remove all checkpoint rows, blobs and pending writes for one thread."""
    if isinstance(saver, PostgresSaver):
        saver.prune([thread_id], strategy="delete")
    else:
        saver.delete_thread(thread_id)


def open_checkpointer() -> tuple[BaseCheckpointSaver, ConnectionPool | None]:
    """Create the checkpointer for the agent graph.

    Returns:
        The saver, plus the connection pool to close on shutdown (None in memory mode).
    """
    url = get_settings().database_url
    if not url:
        # ponytail: in-memory checkpoints are lost on restart; set DATABASE_URL for persistence.
        return InMemorySaver(), None

    # autocommit and prepare_threshold=0 are required by PostgresSaver and by Neon's pooler.
    # check_connection tests pooled connections before checkout so idle connections closed
    # by Neon Serverless Postgres are transparently replaced without a server restart.
    pool = ConnectionPool(
        conninfo=url,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
        check=ConnectionPool.check_connection,
        max_idle=120,
        max_lifetime=600,
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()  # creates checkpoint tables on first run; safe to repeat
    return saver, pool


def ping(pool: ConnectionPool | None) -> str:
    """Report database status for the health endpoint: 'ok', 'memory' or an error string."""
    if pool is None:
        return "memory"
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception as exc:  # health check must report, not raise
        return f"error: {exc.__class__.__name__}"
