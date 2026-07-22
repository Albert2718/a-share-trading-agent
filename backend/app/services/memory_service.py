import json

from app.models import UserMemory
from app.repositories.memory_repository import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository):
        self.repository = repository

    async def context_for_user(self, user_id: str) -> str:
        memories = await self.repository.list_memories(user_id, active_only=True)
        if not memories:
            return "暂无已保存的长期投资偏好。"
        lines = [
            f"- {item.memory_type}.{item.memory_key}: "
            f"{json.dumps(item.memory_value, ensure_ascii=False, default=str)}"
            for item in memories
        ]
        return "用户长期记忆：\n" + "\n".join(lines)

    async def update(self, memory: UserMemory, **changes) -> UserMemory:
        for key, value in changes.items():
            if value is not None:
                setattr(memory, key, value)
        return await self.repository.save(memory)
