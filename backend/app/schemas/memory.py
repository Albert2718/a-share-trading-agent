from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    memory_type: str = Field(min_length=1, max_length=32)
    memory_key: str = Field(min_length=1, max_length=80)
    memory_value: Any
    confidence: float = Field(default=1.0, ge=0, le=1)


class MemoryUpdate(BaseModel):
    memory_value: Any | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    memory_type: str
    memory_key: str
    memory_value: Any
    confidence: float
    status: str
    source_message_id: str | None
    created_at: datetime
    updated_at: datetime
