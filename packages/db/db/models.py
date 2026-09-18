"""SQLAlchemy models — conversations + approve ledger + action_events."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# JSONB on Postgres; plain JSON elsewhere (sqlite unit tests)
_JSON = JSON().with_variant(JSONB(), "postgresql")


class Conversation(Base):
    __tablename__ = "conversations"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, default="research_publish_v1")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running"
    )  # running|interrupted|paused|completed|failed|cancelled
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # plan, pending_action, draft, published, ar_meta, etc.
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_conversations_tenant_user", "tenant_id", "user_id"),
    )


class ApproveLedger(Base):
    """Idempotent approve ledger keyed by (thread_id, pending_action_id, decision)."""

    __tablename__ = "approve_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pending_action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    side_effect_executed: Mapped[bool] = mapped_column(default=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            "pending_action_id",
            "decision",
            name="uq_approve_ledger_thread_action_decision",
        ),
    )


class ActionEventRow(Base):
    """Append-only Action Recording events — survives process restart."""

    __tablename__ = "action_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column("type", String(64), nullable=False)
    specialist: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("thread_id", "seq", name="uq_action_events_thread_seq"),
        Index("ix_action_events_thread_seq", "thread_id", "seq"),
    )
