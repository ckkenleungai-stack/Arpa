"""conversations + approve_ledger

Revision ID: 001
Revises:
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("thread_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("workflow_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index(
        "ix_conversations_tenant_user", "conversations", ["tenant_id", "user_id"]
    )

    op.create_table(
        "approve_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("pending_action_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("side_effect_executed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "thread_id",
            "pending_action_id",
            "decision",
            name="uq_approve_ledger_thread_action_decision",
        ),
    )
    op.create_index("ix_approve_ledger_thread_id", "approve_ledger", ["thread_id"])


def downgrade() -> None:
    op.drop_table("approve_ledger")
    op.drop_table("conversations")
