"""Workflow name → compiled graph."""
from __future__ import annotations

from typing import Any, Callable

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str, factory: Callable[..., Any]) -> None:
    _REGISTRY[name] = factory


def get_graph(name: str, *, checkpointer: Any = None) -> Any:
    if name not in _REGISTRY:
        # Lazy import default
        from workflows.research_publish_v1.graph import build_graph

        register("research_publish_v1", build_graph)
    if name not in _REGISTRY:
        raise KeyError(f"Unknown workflow: {name}")
    return _REGISTRY[name](checkpointer=checkpointer)


def list_workflows() -> list[str]:
    if "research_publish_v1" not in _REGISTRY:
        from workflows.research_publish_v1.graph import build_graph

        register("research_publish_v1", build_graph)
    return sorted(_REGISTRY.keys())
