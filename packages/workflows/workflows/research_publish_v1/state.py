"""Typed state for research_publish_v1."""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class PendingAction(TypedDict, total=False):
    id: str
    kind: Literal["sensitive_tool", "publish"]
    payload: dict[str, Any]
    risk: str
    summary: str


class Approval(TypedDict, total=False):
    decision: Literal["approve", "reject", "edit"]
    edits: dict[str, Any]
    note: str
    actor_user_id: str
    at: str


class ToolResultEntry(TypedDict, total=False):
    name: str
    args_hash: str
    result: Any
    status: str
    specialist: str


class GraphState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    goal: str
    plan: dict[str, Any] | None
    tool_intents: list[dict[str, Any]]
    tool_results: list[ToolResultEntry]
    pending_action: PendingAction | None
    approval: Approval | None
    draft: str | None
    published: bool
    publish_url: str | None
    error: str | None
    specialist: str | None  # G12 chip tag for SSE
