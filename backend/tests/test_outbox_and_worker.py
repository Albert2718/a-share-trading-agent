from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    OutboxEvent,
    Portfolio,
    Position,
    ResearchJob,
    ResearchReport,
    User,
    UserMemory,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.outbox_repository import OutboxRepository
from app.services.knowledge_service import KnowledgeService
from app.services.outbox_service import dispatch_pending_events
from app.services.research_service import _build_personal_context, execute_research_job


@pytest.mark.asyncio
async def test_outbox_dispatch_marks_event_delivered(app_context):
    published = []
    async with app_context["session_maker"]() as session:
        repository = OutboxRepository(session)
        event = await repository.add("research.requested", {"job_id": "job-1"})
        event_id = event.id
        await session.commit()

        def publish(task_name, payload, task_id):
            published.append((task_name, payload, task_id))

        delivered = await dispatch_pending_events(repository, publish)
        assert delivered == 1
        stored = await session.get(OutboxEvent, event_id)
        assert stored.status == "delivered"

    assert published == [
        ("research.run", {"job_id": "job-1"}, f"outbox-{event_id}")
    ]


@pytest.mark.asyncio
async def test_research_worker_claim_is_idempotent(app_context, monkeypatch):
    received_context = {}

    def fake_research(_code, _depth, _risk_profile, personal_context):
        received_context.update(personal_context)
        return {
            "summary": "test report",
            "top_decision": {
                "action": "watch",
                "confidence": Decimal("0.6"),
                "rank_score": 60,
            },
        }

    async with app_context["session_maker"]() as session:
        user = User(email="worker@example.com", username="worker", password_hash="hash")
        session.add(user)
        await session.flush()
        job = ResearchJob(
            user_id=user.id,
            stock_code="600519",
            depth="quick",
            risk_profile="balanced",
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    monkeypatch.setattr(
        "app.services.research_service._run_existing_research",
        fake_research,
    )

    async with app_context["session_maker"]() as session:
        await execute_research_job(session, job_id)
    async with app_context["session_maker"]() as session:
        await execute_research_job(session, job_id)
    async with app_context["session_maker"]() as session:
        reports = await session.scalar(select(func.count()).select_from(ResearchReport))
        stored_job = await session.get(ResearchJob, job_id)

    assert reports == 1
    assert stored_job.status == "completed"
    assert received_context == {
        "target_position": None,
        "portfolio_codes": [],
        "memories": [],
        "knowledge_sources": [],
    }


@pytest.mark.asyncio
async def test_knowledge_index_consumer_is_idempotent(app_context, tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("贵州茅台的主要风险包括需求波动和估值波动。", encoding="utf-8")

    async with app_context["session_maker"]() as session:
        user = User(email="rag@example.com", username="rag", password_hash="hash")
        session.add(user)
        await session.flush()
        document = KnowledgeDocument(
            user_id=user.id,
            filename="report.txt",
            title="测试资料",
            mime_type="text/plain",
            file_path=str(source),
            file_hash="a" * 64,
            file_size=source.stat().st_size,
            status="pending",
            chunk_count=0,
            error="",
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    class FakeVectorStore:
        def __init__(self):
            self.upserts = 0

        async def delete_document(self, _user_id, _document_id):
            return None

        async def upsert_document(self, **_kwargs):
            self.upserts += 1

    vector_store = FakeVectorStore()
    async with app_context["session_maker"]() as session:
        service = KnowledgeService(KnowledgeRepository(session), vector_store=vector_store)
        await service.index_document(document_id)
        await service.index_document(document_id)

    async with app_context["session_maker"]() as session:
        chunk_count = await session.scalar(select(func.count()).select_from(KnowledgeChunk))
        stored = await session.get(KnowledgeDocument, document_id)

    assert vector_store.upserts == 1
    assert chunk_count == 1
    assert stored.status == "ready"


@pytest.mark.asyncio
async def test_research_personal_context_reads_portfolio_and_memory(app_context):
    async with app_context["session_maker"]() as session:
        user = User(email="context@example.com", username="context", password_hash="hash")
        session.add(user)
        await session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        await session.flush()
        session.add(
            Position(
                portfolio_id=portfolio.id,
                stock_code="600519",
                stock_name="贵州茅台",
                quantity=20,
                average_cost=1500,
            )
        )
        session.add(
            UserMemory(
                user_id=user.id,
                memory_type="constraint",
                memory_key="max_drawdown",
                memory_value="10%",
            )
        )
        await session.commit()

        context = await _build_personal_context(session, user.id, "600519")

    assert context["target_position"]["quantity"] == 20
    assert context["target_position"]["average_cost"] == 1500.0
    assert context["memories"][0]["key"] == "max_drawdown"
