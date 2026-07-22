from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_hash(self, user_id: str, file_hash: str) -> KnowledgeDocument | None:
        return await self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.file_hash == file_hash,
            )
        )

    async def create_document(self, **values) -> KnowledgeDocument:
        document = KnowledgeDocument(**values)
        self.session.add(document)
        await self.session.flush()
        return document

    async def list_documents(self, user_id: str) -> list[KnowledgeDocument]:
        rows = await self.session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.user_id == user_id)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        return list(rows)

    async def get_document(self, document_id: str, user_id: str) -> KnowledgeDocument | None:
        return await self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.user_id == user_id,
            )
        )

    async def get_document_for_worker(self, document_id: str) -> KnowledgeDocument | None:
        return await self.session.get(KnowledgeDocument, document_id)

    async def claim_document(self, document_id: str) -> KnowledgeDocument | None:
        result = await self.session.execute(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.status.in_(("pending", "failed")),
            )
            .values(status="processing", error="")
        )
        if result.rowcount != 1:
            return None
        await self.session.flush()
        return await self.session.get(KnowledgeDocument, document_id)

    async def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self.session.flush()
        return document

    async def replace_chunks(self, document_id: str, chunks: list[KnowledgeChunk]) -> None:
        await self.session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        self.session.add_all(chunks)
        await self.session.flush()

    async def delete_document(self, document: KnowledgeDocument) -> None:
        await self.session.delete(document)
        await self.session.flush()
