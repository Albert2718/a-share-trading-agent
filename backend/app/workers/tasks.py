import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.outbox_repository import OutboxRepository
from app.services.knowledge_service import KnowledgeService
from app.services.outbox_service import dispatch_pending_events
from app.services.research_service import execute_research_job
from app.workers.celery_app import celery_app


@celery_app.task(name="research.run", bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def queue_research_job(self, job_id: str) -> None:
    """Execute one durable research job outside the FastAPI process."""
    asyncio.run(_run(job_id))


@celery_app.task(name="knowledge.index", bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def queue_knowledge_document(self, document_id: str) -> None:
    """Parse, chunk, embed and index one uploaded document."""
    asyncio.run(_index_document(document_id))


@celery_app.task(name="outbox.dispatch")
def dispatch_outbox() -> int:
    """Publish committed outbox events to their durable Celery consumers."""
    return asyncio.run(_dispatch_outbox())


async def _run(job_id: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await execute_research_job(session, job_id)
    finally:
        # Each Celery task owns a short-lived event loop. Dispose pooled async
        # connections before that loop closes so no connection is reused by a
        # later task on a different loop.
        await engine.dispose()


async def _index_document(document_id: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await KnowledgeService(KnowledgeRepository(session)).index_document(document_id)
    finally:
        await engine.dispose()


async def _dispatch_outbox() -> int:
    try:
        async with AsyncSessionLocal() as session:
            def publish(task_name: str, payload: dict, task_id: str) -> None:
                celery_app.send_task(task_name, kwargs=payload, task_id=task_id)

            return await dispatch_pending_events(OutboxRepository(session), publish)
    finally:
        await engine.dispose()
