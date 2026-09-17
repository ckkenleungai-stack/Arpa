"""action_events append-only AR log

Revision ID: 002
Revises: 001
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_events",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("at", sa.String(64), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("specialist", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("thread_id", "seq", name="uq_action_events_thread_seq"),
    )
    op.create_index("ix_action_events_thread_id", "action_events", ["thread_id"])
    op.create_index(
        "ix_action_events_thread_seq", "action_events", ["thread_id", "seq"]
    )


def downgrade() -> None:
    op.drop_index("ix_action_events_thread_seq", table_name="action_events")
    op.drop_index("ix_action_events_thread_id", table_name="action_events")
    op.drop_table("action_events")
