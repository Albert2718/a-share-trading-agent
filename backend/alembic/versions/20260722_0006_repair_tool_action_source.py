"""repair source message link on legacy tool actions

Revision ID: 20260722_0006
Revises: 20260722_0005
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op


revision = "20260722_0006"
down_revision = "20260722_0005"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "fk_tool_actions_source_message_id_messages"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tool_actions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("tool_actions")}
    if "source_message_id" in columns:
        return
    with op.batch_alter_table("tool_actions") as batch_op:
        batch_op.add_column(
            sa.Column("source_message_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            CONSTRAINT_NAME,
            "messages",
            ["source_message_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tool_actions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("tool_actions")}
    if "source_message_id" not in columns:
        return
    foreign_keys = {
        constraint.get("name")
        for constraint in inspector.get_foreign_keys("tool_actions")
        if constraint.get("name")
    }
    with op.batch_alter_table("tool_actions") as batch_op:
        if CONSTRAINT_NAME in foreign_keys:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_="foreignkey")
        batch_op.drop_column("source_message_id")
