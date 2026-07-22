import asyncio
import json
import logging
from contextlib import suppress

from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.api.dependencies import CurrentUser, DbSession
from app.repositories.chat_repository import ChatRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.research_repository import ResearchRepository
from app.repositories.tool_action_repository import ToolActionRepository
from app.schemas.chat import ChatMessageCreate, ChatMessageResponse, ConversationResponse
from app.services.chat_service import ChatService


router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def service(session: DbSession) -> ChatService:
    return ChatService(
        ChatRepository(session),
        PortfolioRepository(session),
        ResearchRepository(session),
        MemoryRepository(session),
        KnowledgeRepository(session),
        ToolActionRepository(session),
        OutboxRepository(session),
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(current_user: CurrentUser, session: DbSession):
    conversations = await ChatRepository(session).list_conversations(current_user.id)
    return [
        ConversationResponse(
            id=item.id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
            messages=[],
        )
        for item in conversations
    ]


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(current_user: CurrentUser, session: DbSession):
    conversation = await ChatRepository(session).create_conversation(current_user.id, "新对话")
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, current_user: CurrentUser, session: DbSession):
    conversation = await ChatRepository(session).get_conversation(conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return ConversationResponse.model_validate(conversation)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
async def send_message(conversation_id: str, payload: ChatMessageCreate, current_user: CurrentUser, session: DbSession):
    conversation = await ChatRepository(session).get_conversation(conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    reply = await service(session).respond(conversation_id, current_user, payload.content)
    return ChatMessageResponse.model_validate(reply)


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    conversation = await ChatRepository(session).get_conversation(
        conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        accepting_tokens = True

        def on_token(token: str) -> None:
            if accepting_tokens:
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("token", {"content": token})
                )

        def on_event(event: str, data: dict) -> None:
            if accepting_tokens:
                loop.call_soon_threadsafe(queue.put_nowait, (event, data))

        task = asyncio.create_task(
            service(session).respond(
                conversation_id,
                current_user,
                payload.content,
                on_token=on_token,
                on_event=on_event,
            )
        )
        try:
            while not task.done() or not queue.empty():
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                yield _sse(event, data)
            reply = await task
            response = ChatMessageResponse.model_validate(reply)
            yield _sse("message", response.model_dump(mode="json"))
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise
        except Exception:
            logger.exception(
                "chat stream failed for conversation=%s user=%s",
                conversation_id,
                current_user.id,
            )
            await session.rollback()
            yield _sse("error", {"detail": "消息生成失败，请稍后重试。"})
        finally:
            accepting_tokens = False

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    encoded = jsonable_encoder(data)
    return f"event: {event}\ndata: {json.dumps(encoded, ensure_ascii=False, default=str)}\n\n"


@router.post("/conversations/{conversation_id}/confirm/{message_id}", response_model=ChatMessageResponse)
async def confirm_tool(conversation_id: str, message_id: str, current_user: CurrentUser, session: DbSession):
    conversation = await ChatRepository(session).get_conversation(conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    try:
        reply = await service(session).confirm(conversation_id, message_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatMessageResponse.model_validate(reply)
