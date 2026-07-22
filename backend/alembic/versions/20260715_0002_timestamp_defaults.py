"""add database timestamp defaults

Revision ID: 20260715_0002
Revises: 20260715_0001
Create Date: 2026-07-15
"""

from alembic import op


revision = "20260715_0002"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


TIMESTAMP_TABLES = (
    "users",
    "conversations",
    "portfolios",
    "price_alerts",
    "positions",
    "research_jobs",
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table in TIMESTAMP_TABLES:
        op.execute(f"ALTER TABLE {table} MODIFY created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
        op.execute(f"ALTER TABLE {table} MODIFY updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    for table in ("messages", "research_reports"):
        op.execute(f"ALTER TABLE {table} MODIFY created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table in TIMESTAMP_TABLES:
        op.execute(f"ALTER TABLE {table} MODIFY created_at DATETIME NOT NULL")
        op.execute(f"ALTER TABLE {table} MODIFY updated_at DATETIME NOT NULL")
    for table in ("messages", "research_reports"):
        op.execute(f"ALTER TABLE {table} MODIFY created_at DATETIME NOT NULL")
