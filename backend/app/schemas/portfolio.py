from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PositionCreate(BaseModel):
    stock_code: str = Field(pattern=r"^\d{6}$")
    stock_name: str = Field(default="", max_length=80)
    quantity: int = Field(ge=0)
    average_cost: Decimal = Field(ge=0)


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stock_code: str
    stock_name: str
    quantity: int
    average_cost: Decimal


class PositionSnapshotResponse(PositionResponse):
    cost_value: Decimal
    market_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    pnl_pct: Decimal | None = None
    quote_time: str | None = None
    is_realtime: bool = False
    market_source: str | None = None
    market_error: str | None = None
