from collections.abc import Callable

from app.repositories.outbox_repository import OutboxRepository


EVENT_TASKS = {
    "research.requested": "research.run",
    "knowledge.index_requested": "knowledge.index",
}


async def dispatch_pending_events(
    repository: OutboxRepository,
    publish: Callable[[str, dict, str], None],
    limit: int = 20,
) -> int:
    """Publish committed business events to Celery with an idempotent consumer key."""
    delivered = 0
    for candidate in await repository.pending(limit=limit):
        event = await repository.claim(candidate.id)
        if event is None:
            continue
        task_name = EVENT_TASKS.get(event.event_type)
        if task_name is None:
            await repository.release(event, f"unknown event type: {event.event_type}")
            await repository.session.commit()
            continue
        try:
            publish(task_name, event.payload, f"outbox-{event.id}")
        except Exception as exc:
            await repository.release(event, type(exc).__name__)
            await repository.session.commit()
            continue
        await repository.delivered(event)
        await repository.session.commit()
        delivered += 1
    return delivered
