"""Compile research_publish_v1 graph with checkpointer."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from workflows.research_publish_v1.nodes import (
    hitl_gate_node,
    planner_node,
    publish_node,
    route_after_hitl,
    route_after_planner,
    route_after_synth,
    route_after_tools,
    synthesizer_node,
    tools_node,
)
from workflows.research_publish_v1.state import GraphState


def build_graph(*, checkpointer: Any = None) -> Any:
    g = StateGraph(GraphState)
    g.add_node("planner", planner_node)
    g.add_node("tools", tools_node)
    g.add_node("hitl_gate", hitl_gate_node)
    g.add_node("synthesizer", synthesizer_node)
    g.add_node("publish", publish_node)

    g.set_entry_point("planner")
    g.add_conditional_edges(
        "planner",
        route_after_planner,
        {"tools": "tools", "synthesizer": "synthesizer", "hitl_gate": "hitl_gate"},
    )
    g.add_conditional_edges(
        "tools",
        route_after_tools,
        {"hitl_gate": "hitl_gate", "synthesizer": "synthesizer"},
    )
    g.add_conditional_edges(
        "synthesizer",
        route_after_synth,
        {"hitl_gate": "hitl_gate", "__end__": END},
    )
    g.add_conditional_edges(
        "hitl_gate",
        route_after_hitl,
        {
            "publish": "publish",
            "synthesizer": "synthesizer",
            "hitl_gate": "hitl_gate",
            "__end__": END,
        },
    )
    g.add_edge("publish", END)

    if checkpointer is None:
        try:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()
        except Exception:  # pragma: no cover
            checkpointer = None

    return g.compile(checkpointer=checkpointer)


def get_checkpointer_from_env() -> Any:
    """Prefer PostgresSaver; fall back to MemorySaver when DB unavailable.

    NOTE: PostgresSaver is a checkpointer, NOT a production scheduler.
    Crash resume needs Agent Server workers or Temporal (deferred).
    """
    import os

    sync_url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "")
    if sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    if sync_url.startswith("postgresql://"):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            # Context manager style — for long-lived app we keep connection pool
            saver = PostgresSaver.from_conn_string(sync_url)
            # from_conn_string may return context manager in some versions
            if hasattr(saver, "__enter__"):
                cm = saver
                saver = cm.__enter__()
                # setup tables once
                if hasattr(saver, "setup"):
                    saver.setup()
            elif hasattr(saver, "setup"):
                saver.setup()
            return saver
        except Exception:
            pass

    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
