"""Runs API — create/get/events SSE/resume/pause/resume-run/stop + AR export."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ar.emitter import (
    ActionRecordingEmitter,
    IncompleteRecordingError,
    ScrubError,
    build_stub_recording,
)
from ar.types import missing_required_root
from control_plane.auth import AuthContext, require_auth
from control_plane.deps import (
    acquire_single_flight,
    get_ar_emitter,
    get_compiled_graph,
    get_db,
    is_cancelled,
    release_single_flight,
    set_ar_emitter,
    set_cancel_flag,
)
from db import repo

router = APIRouter(prefix="/v1/runs", tags=["runs"])

# Pause/Stop honesty: v1 in-process cooperative cancel is best-effort.
PAUSE_STOP_SUPPORTED = True  # cooperative flag works in-process; not crash-proof


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreateRunRequest(BaseModel):
    workflow_id: str = "research_publish_v1"
    goal: str = "Research and draft a publishable HTML summary"
    title: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class ResumeRequest(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    edits: dict[str, Any] | None = None
    note: str | None = None


class RunSnapshot(BaseModel):
    thread_id: str
    workflow_id: str
    status: str
    plan: Any = None
    pending_action: Any = None
    draft: str | None = None
    published: bool = False
    publish_url: str | None = None
    title: str | None = None
    specialist: str | None = None


def _snapshot_from_row(row: Any) -> RunSnapshot:
    meta = row.metadata_json or {}
    return RunSnapshot(
        thread_id=row.thread_id,
        workflow_id=row.workflow_id,
        status=row.status,
        plan=meta.get("plan"),
        pending_action=meta.get("pending_action"),
        draft=meta.get("draft"),
        published=bool(meta.get("published", False)),
        publish_url=meta.get("publish_url"),
        title=row.title,
        specialist=meta.get("specialist"),
    )


async def _require_owned(
    session: AsyncSession, thread_id: str, auth: AuthContext
) -> Any:
    row = await repo.get_conversation(
        session, thread_id=thread_id, tenant_id=auth.tenant_id, user_id=auth.user_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _ar_meta_from_emitter(emitter: ActionRecordingEmitter) -> dict[str, Any]:
    return {
        "recording_id": emitter.recording_id,
        "created_at": emitter.created_at,
        "workflow_id": emitter.workflow_id,
        "hitl": list(emitter.hitl),
        "publish": emitter.publish,
        "sources": list(emitter.sources),
        "interview": dict(emitter.interview),
        "plan_summary": emitter.plan_summary,
        "artifacts": dict(emitter.artifacts),
    }


async def _persist_ar(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    emitter: ActionRecordingEmitter,
) -> None:
    """Flush events + AR meta so GET works after process restart."""
    await repo.replace_action_events(
        session, thread_id=thread_id, events=list(emitter.events)
    )
    await repo.update_conversation(
        session,
        thread_id=thread_id,
        tenant_id=tenant_id,
        user_id=user_id,
        metadata_patch={"ar_meta": _ar_meta_from_emitter(emitter)},
    )


async def _hydrate_emitter(
    session: AsyncSession,
    *,
    row: Any,
) -> ActionRecordingEmitter | None:
    """Rebuild emitter from DB when process memory is cold."""
    events = await repo.list_action_events(session, thread_id=row.thread_id)
    meta = row.metadata_json or {}
    ar_meta = meta.get("ar_meta") or {}
    if not events and not ar_meta:
        return None
    emitter = ActionRecordingEmitter(
        thread_id=row.thread_id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        workflow_id=row.workflow_id,
        recording_id=ar_meta.get("recording_id"),
        created_at=ar_meta.get("created_at"),
    )
    if events:
        emitter.load_events(events)
    if ar_meta.get("hitl"):
        emitter.hitl = list(ar_meta["hitl"])
    if ar_meta.get("publish") is not None:
        emitter.publish = ar_meta["publish"]
    if ar_meta.get("sources"):
        emitter.sources = list(ar_meta["sources"])
    if ar_meta.get("interview"):
        emitter.interview = dict(ar_meta["interview"])
    if "plan_summary" in ar_meta:
        emitter.plan_summary = ar_meta.get("plan_summary")
    if ar_meta.get("artifacts"):
        emitter.artifacts = dict(ar_meta["artifacts"])
    set_ar_emitter(row.thread_id, emitter)
    return emitter


async def _get_or_hydrate_emitter(
    session: AsyncSession, *, row: Any
) -> ActionRecordingEmitter | None:
    emitter = get_ar_emitter(row.thread_id)
    if emitter is not None:
        return emitter
    return await _hydrate_emitter(session, row=row)


def _append_hitl_row(
    emitter: ActionRecordingEmitter | None,
    *,
    pending_id: str,
    kind: str,
    decision: str,
    actor_user_id: str,
    edits_applied: bool,
    side_effect_executed: bool,
    idempotency_key: str,
    opened_at: str | None = None,
) -> None:
    if emitter is None:
        return
    emitter.hitl.append(
        {
            "pending_action_id": pending_id,
            "kind": kind,
            "opened_at": opened_at or _utcnow(),
            "closed_at": _utcnow(),
            "decision": decision,
            "actor_user_id": actor_user_id,
            "edits_applied": edits_applied,
            "side_effect_executed": side_effect_executed,
            "idempotency_key": idempotency_key,
        }
    )


async def _persist_state(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    status: str,
    values: dict[str, Any],
) -> None:
    await repo.update_conversation(
        session,
        thread_id=thread_id,
        tenant_id=tenant_id,
        user_id=user_id,
        status=status,
        metadata_patch={
            "plan": values.get("plan"),
            "pending_action": values.get("pending_action"),
            "draft": values.get("draft"),
            "published": values.get("published", False),
            "publish_url": values.get("publish_url"),
            "specialist": values.get("specialist"),
            "error": values.get("error"),
        },
    )


def _status_from_graph_result(result: dict[str, Any], interrupted: bool) -> str:
    if interrupted or result.get("pending_action"):
        return "interrupted"
    if result.get("published"):
        return "completed"
    if result.get("error"):
        return "failed"
    return "running"


def _maybe_hash_draft(emitter: ActionRecordingEmitter | None, draft: str | None) -> None:
    if emitter is None or not draft:
        return
    digest = hashlib.sha256(draft.encode()).hexdigest()
    emitter.artifacts["draft_html_sha256"] = digest


@router.post("")
async def create_run(
    body: CreateRunRequest,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> RunSnapshot:
    thread_id = str(uuid.uuid4())
    await repo.create_conversation(
        session,
        thread_id=thread_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        workflow_id=body.workflow_id,
        title=body.title or body.goal[:80],
        metadata={"goal": body.goal},
    )

    emitter = ActionRecordingEmitter(
        thread_id=thread_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        workflow_id=body.workflow_id,
    )
    emitter.emit(
        "run.started",
        summary="run created",
        payload={"input_ref": body.goal},
        specialist="orchestrator",
    )
    set_ar_emitter(thread_id, emitter)
    set_cancel_flag(thread_id, False)

    graph = get_compiled_graph(body.workflow_id)
    initial: dict[str, Any] = {
        "goal": body.goal,
        "messages": [{"role": "user", "content": body.goal}],
        "tool_results": [],
        "published": False,
    }

    try:
        result = await asyncio.to_thread(
            graph.invoke, initial, config=_config(thread_id)
        )
        state = graph.get_state(_config(thread_id))
        interrupted = bool(state.next) and "hitl_gate" in (state.next or ())
        if getattr(state, "tasks", None):
            for t in state.tasks:
                if getattr(t, "interrupts", None):
                    interrupted = True
                    break
        values = dict(state.values) if state.values else (result or {})
        status = _status_from_graph_result(values, interrupted)
        if interrupted:
            for t in getattr(state, "tasks", []) or []:
                for intr in getattr(t, "interrupts", []) or []:
                    val = getattr(intr, "value", intr)
                    if isinstance(val, dict) and val.get("pending_action"):
                        values["pending_action"] = val["pending_action"]
            emitter.emit(
                "interrupt",
                summary=(values.get("pending_action") or {}).get("summary", "HITL"),
                payload={
                    "kind": (values.get("pending_action") or {}).get("kind"),
                    "pending_action_id": (values.get("pending_action") or {}).get("id"),
                },
                specialist="orchestrator",
            )
            emitter.emit(
                "status",
                summary="→ interrupted",
                payload={"from": "running", "to": "interrupted"},
                specialist="orchestrator",
            )
            # Record interrupt opened_at for later hitl row
            values_meta_opened = _utcnow()
            await repo.update_conversation(
                session,
                thread_id=thread_id,
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                metadata_patch={"interrupt_opened_at": values_meta_opened},
            )
        _maybe_hash_draft(emitter, values.get("draft"))
        await _persist_state(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            status=status,
            values=values,
        )
        await _persist_ar(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            emitter=emitter,
        )
    except Exception as exc:
        emitter.emit(
            "error",
            summary="run error",
            payload={"code": "run_error", "message_scrubbed": str(exc)[:500]},
        )
        await repo.update_conversation(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            status="failed",
            metadata_patch={"error": str(exc)},
        )
        await _persist_ar(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            emitter=emitter,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    row = await _require_owned(session, thread_id, auth)
    return _snapshot_from_row(row)


@router.get("/{thread_id}")
async def get_run(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> RunSnapshot:
    row = await _require_owned(session, thread_id, auth)
    return _snapshot_from_row(row)


@router.get("/{thread_id}/events")
async def stream_events(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE: token/tool/interrupt/status/error with specialist tags."""
    row = await _require_owned(session, thread_id, auth)
    meta = row.metadata_json or {}

    async def event_gen() -> AsyncIterator[str]:
        def sse(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        yield sse(
            "status",
            {
                "status": row.status,
                "specialist": meta.get("specialist") or "orchestrator",
                "thread_id": thread_id,
            },
        )
        if meta.get("plan"):
            yield sse(
                "token",
                {
                    "delta": json.dumps(meta["plan"])[:500],
                    "specialist": "orchestrator",
                },
            )
        if meta.get("pending_action"):
            pa = meta["pending_action"]
            yield sse(
                "interrupt",
                {
                    "kind": pa.get("kind"),
                    "summary": pa.get("summary"),
                    "pending_action": pa,
                    "specialist": "orchestrator",
                },
            )
        if meta.get("draft"):
            yield sse(
                "token",
                {"delta": meta["draft"][:200], "specialist": "writer"},
            )
        emitter = await _get_or_hydrate_emitter(session, row=row)
        if emitter:
            for ev in emitter.events:
                if ev["type"].startswith("tool"):
                    yield sse(
                        "tool",
                        {
                            "summary": ev["summary"],
                            "payload": ev["payload"],
                            "specialist": ev.get("specialist") or "research",
                        },
                    )
        yield sse(
            "status",
            {
                "status": row.status,
                "specialist": meta.get("specialist"),
                "done": True,
            },
        )

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/{thread_id}/resume")
async def resume_hitl(
    thread_id: str,
    body: ResumeRequest,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> RunSnapshot:
    """HITL resume only — approve|reject|edit. Distinct from /resume-run."""
    row = await _require_owned(session, thread_id, auth)
    if row.status != "interrupted":
        raise HTTPException(
            status_code=409,
            detail=f"HITL resume requires status=interrupted (got {row.status})",
        )
    meta = row.metadata_json or {}
    pending = meta.get("pending_action")
    if not pending:
        raise HTTPException(status_code=409, detail="No pending_action to resume")

    pending_id = pending.get("id") or "unknown"
    kind = pending.get("kind") or "publish"
    idem_key = f"{thread_id}:{pending_id}:{body.decision}"

    if not acquire_single_flight(thread_id):
        raise HTTPException(status_code=409, detail="Resume already in flight")

    try:
        emitter = await _get_or_hydrate_emitter(session, row=row)

        # Idempotent approve ledger — re-Approve sets duplicate_suppressed, no side effect
        if body.decision == "approve":
            existing = await repo.find_approve_ledger(
                session,
                thread_id=thread_id,
                pending_action_id=pending_id,
                decision="approve",
            )
            if existing is not None and existing.side_effect_executed:
                if emitter:
                    if kind == "publish":
                        if emitter.publish is None:
                            emitter.publish = {
                                "attempted": True,
                                "url": meta.get("publish_url"),
                                "visibility": "private_invite",
                                "duplicate_suppressed": True,
                            }
                        else:
                            emitter.publish = dict(emitter.publish)
                            emitter.publish["duplicate_suppressed"] = True
                    # Mark hitl row if not already noted for this re-approve
                    _append_hitl_row(
                        emitter,
                        pending_id=pending_id,
                        kind=kind,
                        decision="approve",
                        actor_user_id=auth.user_id,
                        edits_applied=False,
                        side_effect_executed=False,
                        idempotency_key=idem_key,
                        opened_at=meta.get("interrupt_opened_at"),
                    )
                    # Ensure last hitl shows suppressed via publish block; no re-exec
                    await _persist_ar(
                        session,
                        thread_id=thread_id,
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        emitter=emitter,
                    )
                return _snapshot_from_row(row)

        approval = {
            "decision": body.decision,
            "edits": body.edits or {},
            "note": body.note,
            "actor_user_id": auth.user_id,
            "at": _utcnow(),
        }

        if emitter:
            emitter.emit(
                "resume",
                summary=f"HITL {body.decision}",
                payload={
                    "decision": body.decision,
                    "actor_user_id": auth.user_id,
                    "pending_action_id": pending_id,
                },
                specialist="orchestrator",
            )

        graph = get_compiled_graph(row.workflow_id)
        result = await asyncio.to_thread(
            graph.invoke,
            Command(resume=approval),
            config=_config(thread_id),
        )
        state = graph.get_state(_config(thread_id))
        interrupted = bool(state.next)
        if getattr(state, "tasks", None):
            for t in state.tasks:
                if getattr(t, "interrupts", None):
                    interrupted = True
                    break
        values = dict(state.values) if state.values else (result or {})
        if interrupted:
            for t in getattr(state, "tasks", []) or []:
                for intr in getattr(t, "interrupts", []) or []:
                    val = getattr(intr, "value", intr)
                    if isinstance(val, dict) and val.get("pending_action"):
                        values["pending_action"] = val["pending_action"]

        status = _status_from_graph_result(values, interrupted)
        _maybe_hash_draft(emitter, values.get("draft") or meta.get("draft"))

        side_effect = False
        if body.decision == "approve":
            if kind == "publish" and values.get("published"):
                side_effect = True
                html = values.get("draft") or meta.get("draft") or ""
                html_sha = (
                    hashlib.sha256(html.encode()).hexdigest() if html else None
                )
                publish_block = {
                    "attempted": True,
                    "approved_at": _utcnow(),
                    "url": values.get("publish_url"),
                    "visibility": "private_invite",
                    "duplicate_suppressed": False,
                }
                if html_sha:
                    publish_block["html_sha256"] = html_sha
                if emitter:
                    emitter.publish = publish_block
                    if html_sha:
                        emitter.artifacts["published_html_sha256"] = html_sha
                    emitter.artifacts["published_url"] = values.get("publish_url")
                    emitter.emit(
                        "publish",
                        summary="published",
                        payload={"ok": True, "url": values.get("publish_url")},
                        specialist="orchestrator",
                    )
            elif kind == "sensitive_tool":
                side_effect = True

            _append_hitl_row(
                emitter,
                pending_id=pending_id,
                kind=kind,
                decision="approve",
                actor_user_id=auth.user_id,
                edits_applied=bool(body.edits),
                side_effect_executed=side_effect,
                idempotency_key=idem_key,
                opened_at=meta.get("interrupt_opened_at"),
            )
            await repo.record_approve(
                session,
                thread_id=thread_id,
                pending_action_id=pending_id,
                decision="approve",
                idempotency_key=idem_key,
                side_effect_executed=side_effect,
                result_json={"publish_url": values.get("publish_url")},
            )
        elif body.decision == "reject":
            await repo.record_approve(
                session,
                thread_id=thread_id,
                pending_action_id=pending_id,
                decision="reject",
                idempotency_key=idem_key,
                side_effect_executed=False,
                result_json={},
            )
            status = "completed" if values.get("draft") else status
            values["published"] = False
            _append_hitl_row(
                emitter,
                pending_id=pending_id,
                kind=kind,
                decision="reject",
                actor_user_id=auth.user_id,
                edits_applied=False,
                side_effect_executed=False,
                idempotency_key=idem_key,
                opened_at=meta.get("interrupt_opened_at"),
            )
        elif body.decision == "edit":
            _append_hitl_row(
                emitter,
                pending_id=pending_id,
                kind=kind,
                decision="edit",
                actor_user_id=auth.user_id,
                edits_applied=bool(body.edits),
                side_effect_executed=False,
                idempotency_key=idem_key,
                opened_at=meta.get("interrupt_opened_at"),
            )

        await _persist_state(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            status=status,
            values=values,
        )
        if emitter:
            emitter.emit(
                "status",
                summary=f"→ {status}",
                payload={"from": "interrupted", "to": status},
                specialist="orchestrator",
            )
            await _persist_ar(
                session,
                thread_id=thread_id,
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                emitter=emitter,
            )
    finally:
        release_single_flight(thread_id)

    row = await _require_owned(session, thread_id, auth)
    return _snapshot_from_row(row)


@router.post("/{thread_id}/pause")
async def pause_run(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """User pause — NOT HITL. Reject if already interrupted (409)."""
    row = await _require_owned(session, thread_id, auth)
    if row.status == "interrupted":
        raise HTTPException(
            status_code=409,
            detail="Already interrupted — use HITL Approve/Reject/Edit, not Pause",
        )
    if row.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot pause terminal status {row.status}")

    if not PAUSE_STOP_SUPPORTED:
        return {"supported": False, "status": row.status, "thread_id": thread_id}

    set_cancel_flag(thread_id, True)
    await repo.update_conversation(
        session,
        thread_id=thread_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        status="paused",
    )
    emitter = await _get_or_hydrate_emitter(session, row=row)
    if emitter:
        emitter.emit("user.pause", summary="user paused", specialist="orchestrator")
        await _persist_ar(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            emitter=emitter,
        )
    return {"supported": True, "status": "paused", "thread_id": thread_id}


@router.post("/{thread_id}/resume-run")
async def resume_after_pause(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> RunSnapshot:
    """Resume after user Pause only — distinct from HITL /resume."""
    row = await _require_owned(session, thread_id, auth)
    if row.status != "paused":
        raise HTTPException(
            status_code=409,
            detail=f"resume-run requires status=paused (got {row.status})",
        )
    set_cancel_flag(thread_id, False)
    await repo.update_conversation(
        session,
        thread_id=thread_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        status="running",
    )
    graph = get_compiled_graph(row.workflow_id)
    state = graph.get_state(_config(thread_id))
    if state.next:
        try:
            await asyncio.to_thread(graph.invoke, None, config=_config(thread_id))
            state = graph.get_state(_config(thread_id))
            values = dict(state.values) if state.values else {}
            interrupted = bool(state.next)
            status = _status_from_graph_result(values, interrupted)
            await _persist_state(
                session,
                thread_id=thread_id,
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                status=status,
                values=values,
            )
            emitter = await _get_or_hydrate_emitter(session, row=row)
            if emitter:
                await _persist_ar(
                    session,
                    thread_id=thread_id,
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    emitter=emitter,
                )
        except Exception:
            pass
    else:
        await repo.update_conversation(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            status="running",
        )
    row = await _require_owned(session, thread_id, auth)
    return _snapshot_from_row(row)


@router.post("/{thread_id}/stop")
async def stop_run(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await _require_owned(session, thread_id, auth)
    if row.status in ("completed", "cancelled"):
        return {"supported": True, "status": row.status, "thread_id": thread_id}

    if not PAUSE_STOP_SUPPORTED:
        return {"supported": False, "status": row.status, "thread_id": thread_id}

    set_cancel_flag(thread_id, True)
    await repo.update_conversation(
        session,
        thread_id=thread_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        status="cancelled",
    )
    emitter = await _get_or_hydrate_emitter(session, row=row)
    if emitter:
        emitter.emit("user.stop", summary="user stopped", specialist="orchestrator")
        await _persist_ar(
            session,
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            emitter=emitter,
        )
    return {"supported": True, "status": "cancelled", "thread_id": thread_id}


@router.get("/{thread_id}/action-recording")
async def get_action_recording(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """AR export — schema_version arpa.action_recording.v0.

    Fail-closed: missing_required_root nonempty or scrub failure → 500.
    Does NOT claim HG-AUD pass for path Must completeness.
    """
    row = await _require_owned(session, thread_id, auth)
    meta = row.metadata_json or {}
    emitter = await _get_or_hydrate_emitter(session, row=row)

    if emitter is None:
        # Owned thread with no persisted events yet — minimal cold stub only.
        # Do not invent fake history for threads that already ran (those hydrate).
        n = await repo.count_action_events(session, thread_id=thread_id)
        if n > 0:
            raise HTTPException(
                status_code=500,
                detail="action_events present but hydrate failed",
            )
        doc = build_stub_recording(
            thread_id=thread_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            workflow_id=row.workflow_id,
            status=row.status,
            plan_summary=meta.get("plan"),
            publish=(
                {
                    "attempted": True,
                    "url": meta.get("publish_url"),
                    "visibility": "private_invite",
                    "duplicate_suppressed": False,
                }
                if meta.get("published")
                else None
            ),
        )
        missing = missing_required_root(doc)
        if missing:
            raise HTTPException(
                status_code=500,
                detail=f"incomplete action recording: missing {missing}",
            )
        if not (doc.get("integrity") or {}).get("scrubbed"):
            raise HTTPException(
                status_code=500,
                detail="action recording scrub validation failed",
            )
        return doc

    try:
        if meta.get("plan") is not None:
            emitter.plan_summary = meta.get("plan")
        doc = emitter.export(status_at_export=row.status, fail_closed=True)
    except IncompleteRecordingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ScrubError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    out = dict(doc)
    out["_scaffold_note"] = (
        "P0 AR emit wired (tool.*/hitl/scrub/persist). "
        "Do not claim HG-AUD pass until Felix re-evals a GP-1 sample."
    )
    return out
