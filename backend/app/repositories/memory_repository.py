from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserMemory


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_memories(self, user_id: str, *, active_only: bool = False) -> list[UserMemory]:
        query = select(UserMemory).where(UserMemory.user_id == user_id)
        if active_only:
            query = query.where(UserMemory.status == "active")
        rows = await self.session.scalars(
            query.order_by(UserMemory.memory_type, UserMemory.memory_key)
        )
        return list(rows)

    async def get(self, memory_id: str, user_id: str) -> UserMemory | None:
        return await self.session.scalar(
            select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id)
        )

    async def upsert(
        self,
        *,
        user_id: str,
        memory_type: str,
        memory_key: str,
        memory_value,
        confidence: float = 1.0,
        source_message_id: str | None = None,
    ) -> UserMemory:
        memory = await self.session.scalar(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.memory_type == memory_type,
                UserMemory.memory_key == memory_key,
            )
        )
        if memory is None:
            memory = UserMemory(
                user_id=user_id,
                memory_type=memory_type,
                memory_key=memory_key,
                memory_value=memory_value,
                confidence=confidence,
                source_message_id=source_message_id,
            )
            self.session.add(memory)
        else:
            memory.memory_value = memory_value
            memory.confidence = confidence
            memory.status = "active"
            if source_message_id:
                memory.source_message_id = source_message_id
        await self.session.flush()
        return memory

    async def save(self, memory: UserMemory) -> UserMemory:
        await self.session.flush()
        return memory

    async def delete(self, memory_id: str, user_id: str) -> bool:
        result = await self.session.execute(
            delete(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id)
        )
        await self.session.flush()
        return bool(result.rowcount)
