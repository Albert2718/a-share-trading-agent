from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ToolAction


class ToolActionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **values) -> ToolAction:
        action = ToolAction(**values)
        self.session.add(action)
        await self.session.flush()
        return action

    async def get_for_message(
        self, message_id: str, conversation_id: str, user_id: str
    ) -> ToolAction | None:
        return await self.session.scalar(
            select(ToolAction).where(
                ToolAction.message_id == message_id,
                ToolAction.conversation_id == conversation_id,
                ToolAction.user_id == user_id,
            )
        )

    async def latest_pending(
        self, conversation_id: str, user_id: str
    ) -> ToolAction | None:
        """Return the newest write action awaiting a decision in this conversation."""
        return await self.session.scalar(
            select(ToolAction)
            .where(
                ToolAction.conversation_id == conversation_id,
                ToolAction.user_id == user_id,
                ToolAction.status == "pending",
            )
            .order_by(ToolAction.created_at.desc(), ToolAction.id.desc())
            .limit(1)
        )

    async def claim_pending(
        self, message_id: str, conversation_id: str, user_id: str
    ) -> ToolAction | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(ToolAction)
            .where(
                ToolAction.message_id == message_id,
                ToolAction.conversation_id == conversation_id,
                ToolAction.user_id == user_id,
                ToolAction.status == "pending",
            )
            .values(status="executing", confirmed_at=now)
        )
        if result.rowcount != 1:
            return None
        await self.session.flush()
        return await self.get_for_message(message_id, conversation_id, user_id)

    async def complete(self, action: ToolAction, result: dict) -> None:
        action.status = "completed"
        action.result = result
        action.completed_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def cancel_pending(
        self, message_id: str, conversation_id: str, user_id: str
    ) -> ToolAction | None:
        result = await self.session.execute(
            update(ToolAction)
            .where(
                ToolAction.message_id == message_id,
                ToolAction.conversation_id == conversation_id,
                ToolAction.user_id == user_id,
                ToolAction.status == "pending",
            )
            .values(status="cancelled")
        )
        if result.rowcount != 1:
            return None
        await self.session.flush()
        return await self.get_for_message(message_id, conversation_id, user_id)
