from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchJobCreate(BaseModel):
    stock_code: str = Field(pattern=r"^\d{6}$")
    depth: Literal["quick", "standard", "full"] = "standard"
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"


class ResearchJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stock_code: str
    depth: str
    risk_profile: str
    status: str
    progress: int
    error: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ResearchReportResponse(BaseModel):
    id: str
    job_id: str
    action: str
    confidence: float
    rank_score: int
    summary: str
    report_payload: dict[str, Any]
    created_at: datetime
