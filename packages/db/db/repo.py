"""Conversation + AR event repository — always tenant/user filtered for conversations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ActionEventRow, ApproveLedger, Conversation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_conversation(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    workflow_id: str = "research_publish_v1",
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Conversation:
    row = Conversation(
        thread_id=thread_id,
        tenant_id=tenant_id,
        user_id=user_id,
        workflow_id=workflow_id,
        status="running",
        title=title,
        metadata_json=metadata or {},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_conversation(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
) -> Optional[Conversation]:
    stmt = select(Conversation).where(
        Conversation.thread_id == thread_id,
        Conversation.tenant_id == tenant_id,
        Conversation.user_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_conversations(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    limit: int = 50,
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id, Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_conversation(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    status: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
    title: str | None = None,
) -> Optional[Conversation]:
    row = await get_conversation(
        session, thread_id=thread_id, tenant_id=tenant_id, user_id=user_id
    )
    if row is None:
        return None
    if status is not None:
        row.status = status
    if title is not None:
        row.title = title
    if metadata_patch:
        meta = dict(row.metadata_json or {})
        meta.update(metadata_patch)
        row.metadata_json = meta
    row.updated_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def find_approve_ledger(
    session: AsyncSession,
    *,
    thread_id: str,
    pending_action_id: str,
    decision: str,
) -> Optional[ApproveLedger]:
    stmt = select(ApproveLedger).where(
        ApproveLedger.thread_id == thread_id,
        ApproveLedger.pending_action_id == pending_action_id,
        ApproveLedger.decision == decision,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def record_approve(
    session: AsyncSession,
    *,
    thread_id: str,
    pending_action_id: str,
    decision: str,
    idempotency_key: str,
    side_effect_executed: bool,
    result_json: dict[str, Any] | None = None,
) -> ApproveLedger:
    existing = await find_approve_ledger(
        session,
        thread_id=thread_id,
        pending_action_id=pending_action_id,
        decision=decision,
    )
    if existing is not None:
        return existing
    row = ApproveLedger(
        thread_id=thread_id,
        pending_action_id=pending_action_id,
        decision=decision,
        idempotency_key=idempotency_key,
        side_effect_executed=side_effect_executed,
        result_json=result_json or {},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def replace_action_events(
    session: AsyncSession,
    *,
    thread_id: str,
    events: list[dict[str, Any]],
) -> None:
    """Idempotent full replace of action_events for a thread (flush from emitter)."""
    await session.execute(
        delete(ActionEventRow).where(ActionEventRow.thread_id == thread_id)
    )
    for e in events:
        session.add(
            ActionEventRow(
                thread_id=thread_id,
                seq=int(e["seq"]),
                at=str(e.get("at") or ""),
                event_type=str(e.get("type") or "status"),
                specialist=e.get("specialist"),
                summary=str(e.get("summary") or ""),
                payload=dict(e.get("payload") or {}),
            )
        )
    await session.commit()


async def list_action_events(
    session: AsyncSession,
    *,
    thread_id: str,
) -> list[dict[str, Any]]:
    stmt = (
        select(ActionEventRow)
        .where(ActionEventRow.thread_id == thread_id)
        .order_by(ActionEventRow.seq.asc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return [
        {
            "seq": r.seq,
            "at": r.at,
            "type": r.event_type,
            "specialist": r.specialist,
            "summary": r.summary,
            "payload": r.payload or {},
        }
        for r in rows
    ]


async def count_action_events(
    session: AsyncSession,
    *,
    thread_id: str,
) -> int:
    stmt = select(ActionEventRow).where(ActionEventRow.thread_id == thread_id)
    result = await session.execute(stmt)
    return len(list(result.scalars().all()))
