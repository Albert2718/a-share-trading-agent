import asyncio
from functools import lru_cache
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient, models

from app.core.config import PROJECT_ROOT, get_settings
from app.models import KnowledgeDocument
from app.services.document_processing import TextChunk


@lru_cache
def embedding_model() -> TextEmbedding:
    settings = get_settings()
    cache_dir = Path(PROJECT_ROOT / "data" / "models")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=settings.embedding_model, cache_dir=str(cache_dir))


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in embedding_model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(embedding_model().query_embed(text)).tolist()


class VectorStore:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.client = AsyncQdrantClient(url=settings.qdrant_url, timeout=30)

    async def ensure_collection(self) -> None:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            await self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimension,
                    distance=models.Distance.COSINE,
                ),
            )
        for field_name in ("user_id", "document_id", "stock_code", "source_type"):
            await self.client.create_payload_index(
                collection_name=self.settings.qdrant_collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    async def upsert_document(
        self,
        *,
        document: KnowledgeDocument,
        chunks: list[TextChunk],
        point_ids: list[str],
    ) -> None:
        await self.ensure_collection()
        vectors = await asyncio.to_thread(embed_passages, [item.content for item in chunks])
        points = [
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "user_id": document.user_id,
                    "document_id": document.id,
                    "title": document.title,
                    "filename": document.filename,
                    "stock_code": document.stock_code or "",
                    "source_type": document.source_type,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "content": chunk.content,
                },
            )
            for point_id, vector, chunk in zip(point_ids, vectors, chunks, strict=True)
        ]
        await self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=points,
            wait=True,
        )

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
        stock_code: str | None = None,
        source_types: list[str] | None = None,
    ):
        await self.ensure_collection()
        conditions = [
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))
        ]
        if document_ids:
            conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids),
                )
            )
        if stock_code:
            conditions.append(
                models.FieldCondition(key="stock_code", match=models.MatchValue(value=stock_code))
            )
        if source_types:
            conditions.append(
                models.FieldCondition(
                    key="source_type", match=models.MatchAny(any=source_types)
                )
            )
        vector = await asyncio.to_thread(embed_query, query)
        result = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=vector,
            query_filter=models.Filter(must=conditions),
            limit=top_k,
            with_payload=True,
        )
        return result.points

    async def delete_document(self, user_id: str, document_id: str) -> None:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return
        await self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        ),
                    ]
                )
            ),
            wait=True,
        )
