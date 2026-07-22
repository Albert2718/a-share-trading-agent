from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")
    portfolios: Mapped[list[Portfolio]] = relationship(back_populates="user")
    research_jobs: Mapped[list[ResearchJob]] = relationship(back_populates="user")
    alerts: Mapped[list[PriceAlert]] = relationship(back_populates="user")
    memories: Mapped[list[UserMemory]] = relationship(back_populates="user", cascade="all, delete-orphan")
    knowledge_documents: Mapped[list[KnowledgeDocument]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="新对话", nullable=False)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128))
    tool_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Portfolio(TimestampMixin, Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="我的组合", nullable=False)

    user: Mapped[User] = relationship(back_populates="portfolios")
    positions: Mapped[list[Position]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Position(TimestampMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "stock_code", name="uq_positions_portfolio_stock"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True, nullable=False)
    stock_code: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    stock_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)

    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")


class PriceAlert(TimestampMixin, Base):
    __tablename__ = "price_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    stock_code: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    operator: Mapped[str] = mapped_column(String(4), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="alerts")


class ResearchJob(TimestampMixin, Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    stock_code: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    depth: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="research_jobs")
    report: Mapped[ResearchReport | None] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id"), unique=True, nullable=False)
    action: Mapped[str] = mapped_column(String(16), default="watch", nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, nullable=False)
    rank_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped[ResearchJob] = relationship(back_populates="report")


class UserMemory(TimestampMixin, Base):
    __tablename__ = "user_memories"
    __table_args__ = (
        UniqueConstraint("user_id", "memory_type", "memory_key", name="uq_user_memory_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    memory_key: Mapped[str] = mapped_column(String(80), nullable=False)
    memory_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="memories")


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "file_hash", name="uq_knowledge_document_user_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(6), index=True)
    source_type: Mapped[str] = mapped_column(
        String(32), default="other", index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="knowledge_documents")
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class ToolAction(TimestampMixin, Base):
    """Durable, user-confirmed write requested by the Agent."""

    __tablename__ = "tool_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(TimestampMixin, Base):
    """Business event persisted atomically before it is published to Celery."""

    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
