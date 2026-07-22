from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


KnowledgeSourceType = Literal[
    "financial_report",
    "announcement",
    "news",
    "analysis",
    "personal_note",
    "other",
]


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    title: str
    mime_type: str
    file_size: int
    stock_code: str | None
    source_type: KnowledgeSourceType
    status: str
    chunk_count: int
    error: str
    created_at: datetime
    updated_at: datetime


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    stock_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    source_types: list[KnowledgeSourceType] = Field(default_factory=list, max_length=6)
    top_k: int = Field(default=5, ge=1, le=10)


class RagSource(BaseModel):
    document_id: str
    title: str
    filename: str
    source_type: KnowledgeSourceType = "other"
    page_number: int | None
    chunk_index: int
    content: str
    score: float


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagSource]
