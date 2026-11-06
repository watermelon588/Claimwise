"""Observability: LangSmith tracing when a key is set, and a local JSONL timing log of every graph run.

LangSmith reads its settings from the process environment, so setup_tracing() copies them from backend/.env.
The local log (TRACE_LOG) records one line per graph node, model call and tool call: duration, tokens and
errors, tagged with the thread and the API route. e2e/report.py turns it into the performance report.
Only synthetic data may be traced: LangSmith receives prompts, documents and replies.
"""

import json
import os
import threading
import time
from pathlib import Path
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.errors import GraphInterrupt

from app.config import get_settings

_write_lock = threading.Lock()


def setup_tracing() -> bool:
    """Turn on LangSmith tracing when LANGSMITH_API_KEY is configured.

    Returns:
        True when LangSmith tracing is on.
    """
    s = get_settings()
    if not s.langsmith_api_key:
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    if s.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = s.langsmith_endpoint
    return True


class TimingLog(BaseCallbackHandler):
    """Callback that writes one JSON line per node, model call and tool call of a single graph run.

    Args:
        path: JSONL file to append to.
        thread_id: Claim thread the run belongs to.
        route: API route that started the run (chat, upload, action, resume, refresh, stream).
    """

    def __init__(self, path: str, thread_id: str, route: str):
        """Remember where to write and how to tag each line."""
        self.path, self.thread_id, self.route = Path(path), thread_id, route
        self.open: dict[UUID, tuple[str, str, float, dict]] = {}

    def _start(self, run_id: UUID, kind: str, name: str, extra: dict | None = None) -> None:
        """Note when a span started."""
        self.open[run_id] = (kind, name, time.perf_counter(), extra or {})

    def _end(self, run_id: UUID, status: str, **fields) -> None:
        """Write the finished span; spans that were not tracked (nested helpers) are ignored."""
        span = self.open.pop(run_id, None)
        if not span:
            return
        kind, name, started, extra = span
        line = {"at": time.time(), "thread": self.thread_id, "route": self.route, "kind": kind, "name": name,
                "ms": round((time.perf_counter() - started) * 1000, 1), "status": status, **extra, **fields}
        with _write_lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")

    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, **kwargs):
        """Track graph nodes only: the chain whose name is the node name (not chains nested inside it)."""
        node = (metadata or {}).get("langgraph_node")
        if node and kwargs.get("name") == node:
            self._start(run_id, "node", node)

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        """Close a node span."""
        self._end(run_id, "ok")

    def on_chain_error(self, error, *, run_id, **kwargs):
        """Close a node span; an interrupt is a pause for the user, not a failure."""
        paused = isinstance(error, GraphInterrupt)
        self._end(run_id, "paused" if paused else "error", **({} if paused else {"error": error.__class__.__name__}))

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        """Track one model call with its provider and model name."""
        meta = metadata or {}
        self._start(run_id, "llm", meta.get("langgraph_node") or "llm",
                    {"model": meta.get("ls_model_name"), "provider": meta.get("ls_provider")})

    def on_llm_end(self, response, *, run_id, **kwargs):
        """Close a model span with token usage when the provider reports it."""
        usage = {}
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
        except (AttributeError, IndexError):
            pass
        self._end(run_id, "ok", input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))

    def on_llm_error(self, error, *, run_id, **kwargs):
        """Close a model span that failed (the fallback model may still answer)."""
        self._end(run_id, "error", error=error.__class__.__name__)

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        """Track one agent tool call."""
        self._start(run_id, "tool", kwargs.get("name") or (serialized or {}).get("name") or "tool")

    def on_tool_end(self, output, *, run_id, **kwargs):
        """Close a tool span."""
        self._end(run_id, "ok")

    def on_tool_error(self, error, *, run_id, **kwargs):
        """Close a tool span; a pause inside a tool (pack approval) is not a failure."""
        paused = isinstance(error, GraphInterrupt)
        self._end(run_id, "paused" if paused else "error", **({} if paused else {"error": error.__class__.__name__}))


def run_config(thread_id: str, route: str) -> dict:
    """Graph config for one run: the thread, LangSmith run name and metadata, and the local timing log.

    Args:
        thread_id: Claim thread.
        route: API route that started the run.
    Returns:
        A LangGraph config dict.
    """
    trace_log = get_settings().trace_log
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": f"claimwise:{route}",
        "metadata": {"thread_id": thread_id, "route": route},
        "callbacks": [TimingLog(trace_log, thread_id, route)] if trace_log else [],
    }
