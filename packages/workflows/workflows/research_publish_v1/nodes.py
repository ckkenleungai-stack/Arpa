"""Graph nodes — planner → tools → synthesizer + hitl_gate + publish.

HITL rules (Charlotte #3):
- No bare try/except around interrupt()
- No while True interrupt loops
- Side effects before interrupt must be idempotent

AR: tools_node / hitl_gate emit tool.requested + tool.completed|tool.denied
via ar.runtime (digests; folder_jail → tool.denied).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from ar.runtime import (
    emit_tool_outcome,
    emit_tool_requested,
    thread_id_from_config,
)
from tools.builtin import run_tool
from tools.sensitive import is_sensitive, specialist_for
from workflows.research_publish_v1.state import GraphState


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _args_hash(args: dict[str, Any]) -> str:
    blob = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def planner_node(state: GraphState) -> dict[str, Any]:
    """Orchestrator chip — produce plan + tool intents (offline-safe)."""
    goal = state.get("goal") or "Research and draft a publishable HTML summary"
    plan = {
        "steps": [
            {"id": 1, "action": "web_fetch_readonly", "specialist": "research"},
            {"id": 2, "action": "draft_compose", "specialist": "writer"},
            {"id": 3, "action": "publish", "specialist": "orchestrator", "gated": True},
        ],
        "goal": goal,
        "risk": "low",
    }
    tool_intents: list[dict[str, Any]] = []
    if not state.get("tool_results"):
        tool_intents = [
            {"name": "web_fetch_readonly", "args": {"url": "https://example.com"}},
        ]
    messages = list(state.get("messages") or [])
    messages.append(
        {
            "role": "assistant",
            "content": f"Plan ready for: {goal}",
            "specialist": "orchestrator",
        }
    )
    return {
        "plan": plan,
        "tool_intents": tool_intents,
        "messages": messages,
        "specialist": "orchestrator",
        "error": None,
    }


def tools_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Execute non-sensitive tools; queue sensitive for HITL. Emit tool.* AR events."""
    intents = list(state.get("tool_intents") or [])
    results = list(state.get("tool_results") or [])
    sensitive_queued: dict[str, Any] | None = None
    thread_id = thread_id_from_config(config)

    for intent in intents:
        name = intent["name"]
        args = intent.get("args") or {}
        spec = specialist_for(name)
        if is_sensitive(name):
            sensitive_queued = {"name": name, "args": args}
            emit_tool_requested(
                thread_id,
                tool_id=name,
                args=args,
                gated=True,
                specialist=spec,
            )
            break
        ah = _args_hash(args)
        if any(r.get("args_hash") == ah and r.get("status") == "ok" for r in results):
            continue
        emit_tool_requested(
            thread_id,
            tool_id=name,
            args=args,
            gated=False,
            specialist=spec,
        )
        tr = run_tool(name, **args)
        emit_tool_outcome(
            thread_id,
            tool_id=name,
            args=args,
            status=tr.status,
            reason=tr.reason,
            result=tr.result,
            specialist=tr.specialist,
        )
        results.append(
            {
                "name": name,
                "args_hash": ah,
                "result": tr.result,
                "status": tr.status,
                "reason": tr.reason,
                "specialist": tr.specialist,
            }
        )

    out: dict[str, Any] = {
        "tool_results": results,
        "tool_intents": [],
        "specialist": "research",
    }
    if sensitive_queued:
        out["pending_action"] = {
            "id": str(uuid.uuid4()),
            "kind": "sensitive_tool",
            "payload": sensitive_queued,
            "risk": "high",
            "summary": f"Approve sensitive tool: {sensitive_queued['name']}",
        }
    return out


def hitl_gate_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """HITL gate — kinds sensitive_tool | publish only.

    IMPORTANT: interrupt() is NOT wrapped in bare try/except.
    """
    thread_id = thread_id_from_config(config)
    pending = state.get("pending_action")
    if not pending:
        if state.get("draft") and not state.get("published"):
            pending = {
                "id": str(uuid.uuid4()),
                "kind": "publish",
                "payload": {"draft_preview": (state.get("draft") or "")[:500]},
                "risk": "medium",
                "summary": "Approve publish of draft HTML (private invite)",
            }
        else:
            return {"specialist": "orchestrator"}

    kind = pending.get("kind")
    if kind not in ("sensitive_tool", "publish"):
        return {"error": f"invalid HITL kind: {kind}", "pending_action": None}

    decision = interrupt(
        {
            "kind": kind,
            "pending_action": pending,
            "summary": pending.get("summary"),
            "thread_hint": "awaiting HITL",
        }
    )

    approval = decision if isinstance(decision, dict) else {"decision": decision}
    approval.setdefault("at", _utcnow())

    out: dict[str, Any] = {
        "approval": approval,
        "specialist": "orchestrator",
    }

    if approval.get("decision") == "reject":
        out["pending_action"] = None
        return out

    if approval.get("decision") == "edit":
        edits = approval.get("edits") or {}
        if "draft" in edits:
            out["draft"] = edits["draft"]
        out["pending_action"] = pending
        return out

    if kind == "sensitive_tool":
        payload = pending.get("payload") or {}
        name = payload.get("name")
        args = payload.get("args") or {}
        if name:
            spec = specialist_for(name)
            emit_tool_requested(
                thread_id,
                tool_id=name,
                args=args,
                gated=True,
                specialist=spec,
            )
            tr = run_tool(name, **args)
            emit_tool_outcome(
                thread_id,
                tool_id=name,
                args=args,
                status=tr.status,
                reason=tr.reason,
                result=tr.result,
                specialist=tr.specialist,
            )
            results = list(state.get("tool_results") or [])
            results.append(
                {
                    "name": name,
                    "args_hash": _args_hash(args),
                    "result": tr.result,
                    "status": tr.status,
                    "reason": tr.reason,
                    "specialist": tr.specialist,
                }
            )
            out["tool_results"] = results
        out["pending_action"] = None
    elif kind == "publish":
        out["pending_action"] = pending
    return out


def synthesizer_node(state: GraphState) -> dict[str, Any]:
    """Writer chip — produce draft HTML from plan + tool_results."""
    plan = state.get("plan") or {}
    results = state.get("tool_results") or []
    excerpts = []
    for r in results:
        if r.get("status") == "ok":
            excerpts.append(str(r.get("result")))
    body = (
        "<html><body>"
        "<h1>Arpa Research Draft</h1>"
        f"<p>Goal: {plan.get('goal', '')}</p>"
        f"<pre>{chr(10).join(excerpts[:5])}</pre>"
        "<p><em>Draft — not published</em></p>"
        "</body></html>"
    )
    if state.get("approval") and (state["approval"] or {}).get("edits", {}).get("draft"):
        body = state["approval"]["edits"]["draft"]  # type: ignore[index]

    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": "Draft ready", "specialist": "writer"})
    return {
        "draft": body,
        "messages": messages,
        "specialist": "writer",
        "published": False,
    }


def publish_node(state: GraphState) -> dict[str, Any]:
    """Publish only after approve — API layer enforces idempotent ledger."""
    approval = state.get("approval") or {}
    if approval.get("decision") != "approve":
        return {"published": False, "specialist": "orchestrator"}

    if state.get("published") and state.get("publish_url"):
        return {
            "published": True,
            "publish_url": state["publish_url"],
            "specialist": "orchestrator",
        }

    url = f"https://arpa.local/private/{uuid.uuid4().hex[:12]}"
    return {
        "published": True,
        "publish_url": url,
        "pending_action": None,
        "specialist": "orchestrator",
    }


def route_after_planner(state: GraphState) -> str:
    if state.get("tool_intents"):
        return "tools"
    if state.get("draft") and not state.get("published"):
        return "hitl_gate"
    if state.get("tool_results") and not state.get("draft"):
        return "synthesizer"
    return "synthesizer"


def route_after_tools(state: GraphState) -> str:
    if state.get("pending_action"):
        return "hitl_gate"
    return "synthesizer"


def route_after_hitl(state: GraphState) -> str:
    approval = state.get("approval") or {}
    pending = state.get("pending_action")
    decision = approval.get("decision")

    if decision == "reject":
        return "__end__"
    if pending and pending.get("kind") == "publish" and decision == "approve":
        return "publish"
    if decision == "approve" and not state.get("draft"):
        return "synthesizer"
    if state.get("draft") and not state.get("published"):
        if pending and pending.get("kind") == "publish":
            return "publish"
        return "hitl_gate"
    if state.get("published"):
        return "__end__"
    return "synthesizer"


def route_after_synth(state: GraphState) -> str:
    if state.get("draft") and not state.get("published"):
        return "hitl_gate"
    return "__end__"
