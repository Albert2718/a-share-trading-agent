import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from src.core import get_llm_client

from app.core.config import get_settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.knowledge import KnowledgeSourceType, RagSource
from app.services.document_processing import parse_document, split_pages
from app.services.vector_store import VectorStore


ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        vector_store: VectorStore | None = None,
        outbox: OutboxRepository | None = None,
    ):
        self.repository = repository
        self.vector_store = vector_store or VectorStore()
        self.outbox = outbox

    async def create_upload(
        self,
        *,
        user_id: str,
        upload: UploadFile,
        title: str | None,
        stock_code: str | None,
        source_type: KnowledgeSourceType = "other",
    ) -> KnowledgeDocument:
        filename = Path(upload.filename or "document").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("仅支持 PDF、Markdown 和 TXT 文档")
        data = await upload.read()
        settings = get_settings()
        if not data:
            raise ValueError("上传文件为空")
        if len(data) > settings.max_upload_size_mb * 1024 * 1024:
            raise ValueError(f"文件不能超过 {settings.max_upload_size_mb} MB")
        file_hash = hashlib.sha256(data).hexdigest()
        existing = await self.repository.find_by_hash(user_id, file_hash)
        if existing:
            raise ValueError("该文档已经上传")
        document_id = str(uuid.uuid4())
        directory = Path(settings.upload_dir) / user_id / document_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        await asyncio.to_thread(path.write_bytes, data)
        document = await self.repository.create_document(
            id=document_id,
            user_id=user_id,
            filename=filename,
            title=(title or Path(filename).stem).strip()[:255],
            mime_type=upload.content_type or "application/octet-stream",
            file_path=str(path),
            file_hash=file_hash,
            file_size=len(data),
            stock_code=stock_code or None,
            source_type=source_type,
            status="pending",
            chunk_count=0,
            error="",
        )
        if self.outbox is not None:
            await self.outbox.add(
                "knowledge.index_requested", {"document_id": document.id}
            )
        return document

    async def index_document(self, document_id: str) -> None:
        document = await self.repository.claim_document(document_id)
        if document is None:
            return
        await self.repository.session.commit()
        try:
            pages = await asyncio.to_thread(parse_document, Path(document.file_path))
            chunks = await asyncio.to_thread(split_pages, pages)
            if not chunks:
                raise ValueError("文档中没有提取到可索引文本")
            point_ids = [str(uuid.uuid4()) for _ in chunks]
            await self.vector_store.delete_document(document.user_id, document.id)
            await self.vector_store.upsert_document(
                document=document,
                chunks=chunks,
                point_ids=point_ids,
            )
            records = [
                KnowledgeChunk(
                    document_id=document.id,
                    qdrant_point_id=point_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    chunk_metadata={
                        "filename": document.filename,
                        "source_type": document.source_type,
                    },
                )
                for point_id, chunk in zip(point_ids, chunks, strict=True)
            ]
            await self.repository.replace_chunks(document.id, records)
            document.chunk_count = len(records)
            document.status = "ready"
        except Exception as exc:
            document.status = "failed"
            document.error = str(exc)[:1000]
        await self.repository.save_document(document)
        await self.repository.session.commit()

    async def delete_document(self, document: KnowledgeDocument) -> None:
        await self.vector_store.delete_document(document.user_id, document.id)
        path = Path(document.file_path)
        await self.repository.delete_document(document)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def search(
        self,
        *,
        user_id: str,
        question: str,
        document_ids: list[str] | None = None,
        stock_code: str | None = None,
        source_types: list[KnowledgeSourceType] | None = None,
        top_k: int = 5,
    ) -> list[RagSource]:
        points = await self.vector_store.search(
            user_id=user_id,
            query=question,
            top_k=top_k,
            document_ids=document_ids,
            stock_code=stock_code,
            source_types=source_types,
        )
        sources = []
        for point in points:
            payload = point.payload or {}
            sources.append(
                RagSource(
                    document_id=str(payload.get("document_id", "")),
                    title=str(payload.get("title", "")),
                    filename=str(payload.get("filename", "")),
                    source_type=str(payload.get("source_type", "other")),
                    page_number=payload.get("page_number"),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    content=str(payload.get("content", "")),
                    score=float(point.score),
                )
            )
        return sources

    async def answer(self, *, user_id: str, question: str, **filters):
        sources = await self.search(user_id=user_id, question=question, **filters)
        if not sources:
            return "没有在你的知识库中检索到相关内容。", []
        context = "\n\n".join(
            f"[{index}] {item.title}，页码 {item.page_number or '未知'}\n{item.content}"
            for index, item in enumerate(sources, start=1)
        )
        answer = await asyncio.to_thread(_answer_with_context, question, context)
        return answer, sources


def _answer_with_context(question: str, context: str) -> str:
    return get_llm_client().chat(
        [
            {
                "role": "system",
                "content": (
                    "你是投研知识库助手。只能根据提供的检索片段回答；"
                    "每个事实后使用 [1]、[2] 形式标注来源。若材料不足必须明确说明。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{question}\n\n检索材料：\n{context}",
            },
        ],
        temperature=0.1,
    ) or "已检索到材料，但未生成可用回答。"
