"""Conversations CRUD — tenant filtered."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.auth import AuthContext, require_auth
from control_plane.deps import get_db
from db import repo

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    thread_id: str
    tenant_id: str
    user_id: str
    workflow_id: str
    status: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_mine(
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    rows = await repo.list_conversations(
        session, tenant_id=auth.tenant_id, user_id=auth.user_id
    )
    return [
        ConversationOut(
            thread_id=r.thread_id,
            tenant_id=r.tenant_id,
            user_id=r.user_id,
            workflow_id=r.workflow_id,
            status=r.status,
            title=r.title,
            metadata=r.metadata_json or {},
        )
        for r in rows
    ]


@router.get("/{thread_id}")
async def get_one(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db),
) -> ConversationOut:
    row = await repo.get_conversation(
        session, thread_id=thread_id, tenant_id=auth.tenant_id, user_id=auth.user_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationOut(
        thread_id=row.thread_id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        workflow_id=row.workflow_id,
        status=row.status,
        title=row.title,
        metadata=row.metadata_json or {},
    )
