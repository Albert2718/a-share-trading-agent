from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Conversation, Message


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(self, user_id: str, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title[:255] or "新对话")
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_conversation(self, conversation_id: str, user_id: str) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_conversations(self, user_id: str) -> list[Conversation]:
        rows = await self.session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        )
        return list(rows)

    async def recent_messages(self, conversation_id: str, limit: int = 20) -> list[Message]:
        rows = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_payload: dict | None = None,
        *,
        message_id: str | None = None,
    ) -> Message:
        message = Message(
            **({"id": message_id} if message_id else {}),
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_payload=tool_payload,
        )
        self.session.add(message)
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
        await self.session.flush()
        return message

    async def get_message(self, message_id: str, conversation_id: str) -> Message | None:
        return await self.session.scalar(
            select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
        )

    async def save(self, message: Message) -> None:
        await self.session.flush()
