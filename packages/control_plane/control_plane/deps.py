"""FastAPI dependencies — DB session, graph runtime, AR emitter registry."""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ar.runtime import clear_emitters, get_emitter, set_emitter
from db.session import get_session_factory, init_engine

# Process-local runtime state (W1 in-process — not a durable scheduler)
_graphs: dict[str, Any] = {}
_checkpointer: Any = None
_run_tasks: dict[str, Any] = {}  # thread_id → cooperative cancel flag
_single_flight: dict[str, bool] = {}


def get_checkpointer() -> Any:
    global _checkpointer
    if _checkpointer is None:
        from workflows.research_publish_v1.graph import get_checkpointer_from_env

        _checkpointer = get_checkpointer_from_env()
    return _checkpointer


def get_compiled_graph(workflow_id: str = "research_publish_v1") -> Any:
    if workflow_id not in _graphs:
        from workflows.registry import get_graph

        _graphs[workflow_id] = get_graph(workflow_id, checkpointer=get_checkpointer())
    return _graphs[workflow_id]


def reset_runtime_for_tests(*, use_memory: bool = True) -> None:
    """Reset process state; force MemorySaver for unit tests."""
    global _checkpointer, _graphs, _run_tasks, _single_flight
    _graphs = {}
    _run_tasks = {}
    _single_flight = {}
    clear_emitters()
    if use_memory:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
    else:
        _checkpointer = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def ensure_db_initialized(database_url: str | None = None) -> None:
    url = database_url or os.environ.get("DATABASE_URL")
    if url:
        init_engine(url)


def get_ar_emitter(thread_id: str) -> Any | None:
    return get_emitter(thread_id)


def set_ar_emitter(thread_id: str, emitter: Any) -> None:
    set_emitter(thread_id, emitter)


def acquire_single_flight(thread_id: str) -> bool:
    if _single_flight.get(thread_id):
        return False
    _single_flight[thread_id] = True
    return True


def release_single_flight(thread_id: str) -> None:
    _single_flight.pop(thread_id, None)


def set_cancel_flag(thread_id: str, value: bool = True) -> None:
    _run_tasks[thread_id] = {"cancel": value}


def is_cancelled(thread_id: str) -> bool:
    return bool((_run_tasks.get(thread_id) or {}).get("cancel"))
