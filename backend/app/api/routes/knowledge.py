import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import CurrentUser, DbSession
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeSourceType,
    RagQueryRequest,
    RagQueryResponse,
)
from app.services.knowledge_service import KnowledgeService


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
async def list_documents(current_user: CurrentUser, session: DbSession):
    documents = await KnowledgeRepository(session).list_documents(current_user.id)
    return [KnowledgeDocumentResponse.model_validate(item) for item in documents]


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    current_user: CurrentUser,
    session: DbSession,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    stock_code: str | None = Form(default=None),
    source_type: KnowledgeSourceType = Form(default="other"),
):
    if stock_code and not re.fullmatch(r"\d{6}", stock_code):
        raise HTTPException(status_code=400, detail="股票代码必须是 6 位数字")
    try:
        document = await KnowledgeService(
            KnowledgeRepository(session), outbox=OutboxRepository(session)
        ).create_upload(
            user_id=current_user.id,
            upload=file,
            title=title,
            stock_code=stock_code,
            source_type=source_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KnowledgeDocumentResponse.model_validate(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, current_user: CurrentUser, session: DbSession):
    repository = KnowledgeRepository(session)
    document = await repository.get_document(document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    await KnowledgeService(repository).delete_document(document)


@router.post("/query", response_model=RagQueryResponse)
async def query_knowledge(
    payload: RagQueryRequest,
    current_user: CurrentUser,
    session: DbSession,
):
    answer, sources = await KnowledgeService(KnowledgeRepository(session)).answer(
        user_id=current_user.id,
        **payload.model_dump(),
    )
    return RagQueryResponse(answer=answer, sources=sources)
