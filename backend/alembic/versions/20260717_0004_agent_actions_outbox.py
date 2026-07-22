"""add durable agent actions and transactional outbox

Revision ID: 20260717_0004
Revises: 20260716_0003
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op


revision = "20260717_0004"
down_revision = "20260716_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "tool_actions" not in existing_tables:
        op.create_table(
        "tool_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        )
        op.create_index("ix_tool_actions_user_id", "tool_actions", ["user_id"])
        op.create_index("ix_tool_actions_conversation_id", "tool_actions", ["conversation_id"])
        op.create_index("ix_tool_actions_tool_name", "tool_actions", ["tool_name"])
        op.create_index("ix_tool_actions_status", "tool_actions", ["status"])

    if "outbox_events" not in existing_tables:
        op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
        op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
        op.create_index("ix_outbox_events_available_at", "outbox_events", ["available_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_available_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_tool_actions_status", table_name="tool_actions")
    op.drop_index("ix_tool_actions_tool_name", table_name="tool_actions")
    op.drop_index("ix_tool_actions_conversation_id", table_name="tool_actions")
    op.drop_index("ix_tool_actions_user_id", table_name="tool_actions")
    op.drop_table("tool_actions")
