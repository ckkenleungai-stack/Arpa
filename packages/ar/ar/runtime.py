"""Process-local AR emitter registry — shared by control_plane + graph nodes.

Keeps workflows from importing control_plane while still allowing tools_node
to emit tool.* events against the same ActionRecordingEmitter.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from ar.emitter import ActionRecordingEmitter

_emitters: dict[str, ActionRecordingEmitter] = {}
# Optional async persist hook: (thread_id, emitter) -> None — set by control_plane
_persist_hook: Callable[[str, ActionRecordingEmitter], Any] | None = None


def get_emitter(thread_id: str) -> ActionRecordingEmitter | None:
    return _emitters.get(thread_id)


def set_emitter(thread_id: str, emitter: ActionRecordingEmitter) -> None:
    _emitters[thread_id] = emitter


def clear_emitters() -> None:
    _emitters.clear()


def set_persist_hook(hook: Callable[[str, ActionRecordingEmitter], Any] | None) -> None:
    global _persist_hook
    _persist_hook = hook


def args_digest(args: dict[str, Any] | None) -> str:
    blob = json.dumps(args or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def result_digest(result: Any) -> str:
    blob = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def emit_tool_requested(
    thread_id: str | None,
    *,
    tool_id: str,
    args: dict[str, Any] | None = None,
    gated: bool = False,
    specialist: str | None = None,
) -> None:
    if not thread_id:
        return
    emitter = get_emitter(thread_id)
    if emitter is None:
        return
    digest = args_digest(args)
    emitter.emit(
        "tool.requested",
        summary=f"tool requested: {tool_id}",
        payload={"tool_id": tool_id, "args_digest": digest, "gated": gated},
        specialist=specialist,
    )


def emit_tool_outcome(
    thread_id: str | None,
    *,
    tool_id: str,
    args: dict[str, Any] | None = None,
    status: str,
    reason: str | None = None,
    result: Any = None,
    specialist: str | None = None,
) -> None:
    """Emit tool.completed or tool.denied after run_tool.

    Jail deny Must: status==denied + reason==folder_jail → tool.denied with
    payload={tool_id, reason: "folder_jail"}.
    """
    if not thread_id:
        return
    emitter = get_emitter(thread_id)
    if emitter is None:
        return
    digest = args_digest(args)
    if status == "denied":
        payload: dict[str, Any] = {"tool_id": tool_id, "reason": reason or "denied"}
        if reason == "folder_jail":
            payload["reason"] = "folder_jail"
        emitter.emit(
            "tool.denied",
            summary=f"tool denied: {tool_id}" + (f" ({reason})" if reason else ""),
            payload=payload,
            specialist=specialist,
        )
        return
    ok = status == "ok"
    emitter.emit(
        "tool.completed",
        summary=f"tool completed: {tool_id}",
        payload={
            "tool_id": tool_id,
            "args_digest": digest,
            "ok": ok,
            "result_digest": result_digest(result),
        },
        specialist=specialist,
    )


def thread_id_from_config(config: Any) -> str | None:
    if not config:
        return None
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        tid = cfg.get("thread_id")
        return str(tid) if tid else None
    # RunnableConfig-like
    configurable = getattr(config, "get", None)
    if callable(configurable):
        cfg = config.get("configurable") or {}
        tid = cfg.get("thread_id")
        return str(tid) if tid else None
    return None
