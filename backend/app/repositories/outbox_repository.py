from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event_type: str, payload: dict) -> OutboxEvent:
        event = OutboxEvent(event_type=event_type, payload=payload)
        self.session.add(event)
        await self.session.flush()
        return event

    async def pending(self, limit: int = 20) -> list[OutboxEvent]:
        rows = await self.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.available_at <= datetime.now(timezone.utc),
            )
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        return list(rows)

    async def claim(self, event_id: str) -> OutboxEvent | None:
        result = await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.status == "pending")
            .values(status="processing", attempts=OutboxEvent.attempts + 1)
        )
        if result.rowcount != 1:
            return None
        await self.session.flush()
        return await self.session.get(OutboxEvent, event_id)

    async def delivered(self, event: OutboxEvent) -> None:
        event.status = "delivered"
        event.delivered_at = datetime.now(timezone.utc)
        event.last_error = ""
        await self.session.flush()

    async def release(self, event: OutboxEvent, error: str) -> None:
        event.status = "pending"
        event.last_error = error[:500]
        await self.session.flush()
