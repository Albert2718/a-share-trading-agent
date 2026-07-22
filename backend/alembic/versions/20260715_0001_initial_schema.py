"""initial platform schema

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260715_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("risk_profile", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=128)),
        sa.Column("tool_payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stock_code", sa.String(length=6), nullable=False),
        sa.Column("operator", sa.String(length=4), nullable=False),
        sa.Column("target_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
    op.create_index("ix_price_alerts_stock_code", "price_alerts", ["stock_code"])
    op.create_table(
        "positions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("portfolio_id", sa.String(length=36), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("stock_code", sa.String(length=6), nullable=False),
        sa.Column("stock_name", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_cost", sa.Numeric(14, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("portfolio_id", "stock_code", name="uq_positions_portfolio_stock"),
    )
    op.create_index("ix_positions_portfolio_id", "positions", ["portfolio_id"])
    op.create_index("ix_positions_stock_code", "positions", ["stock_code"])
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stock_code", sa.String(length=6), nullable=False),
        sa.Column("depth", sa.String(length=16), nullable=False),
        sa.Column("risk_profile", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_research_jobs_user_id", "research_jobs", ["user_id"])
    op.create_index("ix_research_jobs_stock_code", "research_jobs", ["stock_code"])
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])
    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("research_jobs.id"), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("rank_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("llm_provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("job_id"),
    )


def downgrade() -> None:
    op.drop_table("research_reports")
    op.drop_index("ix_research_jobs_status", table_name="research_jobs")
    op.drop_index("ix_research_jobs_stock_code", table_name="research_jobs")
    op.drop_index("ix_research_jobs_user_id", table_name="research_jobs")
    op.drop_table("research_jobs")
    op.drop_index("ix_price_alerts_stock_code", table_name="price_alerts")
    op.drop_index("ix_price_alerts_user_id", table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index("ix_positions_stock_code", table_name="positions")
    op.drop_index("ix_positions_portfolio_id", table_name="positions")
    op.drop_table("positions")
    op.drop_index("ix_portfolios_user_id", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
