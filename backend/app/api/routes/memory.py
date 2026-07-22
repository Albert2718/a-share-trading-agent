from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DbSession
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_service import MemoryService


router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryResponse])
async def list_memories(current_user: CurrentUser, session: DbSession):
    memories = await MemoryRepository(session).list_memories(current_user.id)
    return [MemoryResponse.model_validate(item) for item in memories]


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(payload: MemoryCreate, current_user: CurrentUser, session: DbSession):
    memory = await MemoryRepository(session).upsert(
        user_id=current_user.id,
        **payload.model_dump(),
    )
    return MemoryResponse.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    current_user: CurrentUser,
    session: DbSession,
):
    repository = MemoryRepository(session)
    memory = await repository.get(memory_id, current_user.id)
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    memory = await MemoryService(repository).update(
        memory,
        **payload.model_dump(exclude_unset=True),
    )
    return MemoryResponse.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, current_user: CurrentUser, session: DbSession):
    deleted = await MemoryRepository(session).delete(memory_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记忆不存在")
