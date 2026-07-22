"""add knowledge document source type

Revision ID: 20260722_0005
Revises: 20260717_0004
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op


revision = "20260722_0005"
down_revision = "20260717_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("knowledge_documents")
    }
    if "source_type" not in columns:
        with op.batch_alter_table("knowledge_documents") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "source_type",
                    sa.String(length=32),
                    nullable=False,
                    server_default="other",
                )
            )
            batch_op.create_index(
                "ix_knowledge_documents_source_type", ["source_type"]
            )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.drop_index("ix_knowledge_documents_source_type")
        batch_op.drop_column("source_type")
