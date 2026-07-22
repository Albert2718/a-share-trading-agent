from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResearchReport
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.research_repository import ResearchRepository
from app.services.knowledge_service import KnowledgeService


class ResearchService:
    def __init__(self, repository: ResearchRepository, outbox: OutboxRepository | None = None):
        self.repository = repository
        self.outbox = outbox

    async def submit(self, *, user_id: str, stock_code: str, depth: str, risk_profile: str):
        job = await self.repository.create_job(
            user_id=user_id,
            stock_code=stock_code,
            depth=depth,
            risk_profile=risk_profile,
        )
        if self.outbox is not None:
            await self.outbox.add("research.requested", {"job_id": job.id})
        return job


async def execute_research_job(session: AsyncSession, job_id: str) -> None:
    """Run the existing research core from a Celery worker and persist its result."""
    repository = ResearchRepository(session)
    job = await repository.claim_job(job_id)
    if job is None:
        return
    await session.commit()

    try:
        personal_context = await _build_personal_context(session, job.user_id, job.stock_code)
        report_data = await asyncio.to_thread(
            _run_existing_research,
            job.stock_code,
            job.depth,
            job.risk_profile,
            personal_context,
        )
        decision = report_data.get("top_decision") or {}
        job.progress = 90
        await repository.save(job)
        await session.commit()
        await repository.create_report(
            ResearchReport(
                job_id=job.id,
                action=str(decision.get("action", "watch")),
                confidence=Decimal(str(decision.get("confidence", 0))),
                rank_score=int(decision.get("rank_score", 0) or 0),
                summary=str(report_data.get("summary", "")),
                report_payload=_json_safe(report_data),
            )
        )
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        await repository.save(job)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed_job = await repository.get_job_for_worker(job_id)
        if failed_job is not None:
            failed_job.status = "failed"
            failed_job.error = type(exc).__name__
            failed_job.completed_at = datetime.now(timezone.utc)
            await repository.save(failed_job)
            await session.commit()
        raise


async def _build_personal_context(
    session: AsyncSession,
    user_id: str,
    stock_code: str,
) -> dict[str, Any]:
    positions = await PortfolioRepository(session).list_positions(user_id)
    memories = await MemoryRepository(session).list_memories(user_id, active_only=True)
    target = next((item for item in positions if item.stock_code == stock_code), None)
    documents = await KnowledgeRepository(session).list_documents(user_id)
    has_searchable_documents = any(
        item.status == "ready" and item.stock_code in (None, stock_code)
        for item in documents
    )
    sources = []
    if has_searchable_documents:
        try:
            sources = await KnowledgeService(KnowledgeRepository(session)).search(
                user_id=user_id,
                question=f"{stock_code} 投资价值、主要风险、业绩与估值",
                stock_code=stock_code,
                top_k=5,
            )
            if not sources:
                sources = await KnowledgeService(KnowledgeRepository(session)).search(
                    user_id=user_id,
                    question=f"{stock_code} 投资价值、主要风险、业绩与估值",
                    top_k=5,
                )
        except Exception:
            sources = []
    return {
        "target_position": (
            {
                "stock_code": target.stock_code,
                "stock_name": target.stock_name,
                "quantity": target.quantity,
                "average_cost": float(target.average_cost),
            }
            if target
            else None
        ),
        "portfolio_codes": [item.stock_code for item in positions[:30]],
        "memories": [
            {
                "type": item.memory_type,
                "key": item.memory_key,
                "value": _json_safe(item.memory_value),
                "confidence": item.confidence,
            }
            for item in memories[:30]
        ],
        "knowledge_sources": [item.model_dump(mode="json") for item in sources],
    }


def _run_existing_research(
    code: str,
    depth: str,
    risk_profile: str,
    personal_context: dict[str, Any] | None = None,
) -> dict:
    """Compatibility adapter around the existing course-project research core."""
    from src.tools.deep_research import run_deep_research

    return run_deep_research(
        code=code,
        depth=depth,
        risk_profile=risk_profile,
        personal_context=personal_context,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
