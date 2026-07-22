import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.research_repository import ResearchRepository
from app.schemas.knowledge import KnowledgeSourceType
from app.services.knowledge_service import KnowledgeService
from app.services.portfolio_service import PortfolioService
from app.services.research_service import ResearchService
from src.tools.market import get_daily_price, get_realtime_price

from .specs import AsyncToolRegistry, ToolEffect, ToolSpec


class EmptyArgs(BaseModel):
    pass


class MarketQuoteArgs(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MarketHistoryArgs(MarketQuoteArgs):
    days: int = Field(default=30, ge=5, le=90)


class PortfolioUpsertArgs(BaseModel):
    stock_code: str = Field(pattern=r"^\d{6}$")
    stock_name: str = Field(default="", max_length=80)
    quantity: int = Field(ge=0)
    average_cost: float = Field(ge=0)


class ResearchSubmitArgs(BaseModel):
    stock_code: str = Field(pattern=r"^\d{6}$")
    depth: str = Field(default="standard", pattern=r"^(quick|standard|full)$")
    risk_profile: str | None = Field(
        default=None, pattern=r"^(conservative|balanced|aggressive)$"
    )


class MemoryUpsertArgs(BaseModel):
    memory_type: str = Field(pattern=r"^(profile|preference|constraint|watchlist)$")
    memory_key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    memory_value: Any
    confidence: float = Field(default=1.0, ge=0, le=1)


class KnowledgeSearchArgs(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    stock_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    source_types: list[KnowledgeSourceType] = Field(default_factory=list, max_length=6)
    top_k: int = Field(default=5, ge=1, le=10)


@dataclass(frozen=True)
class WebToolContext:
    user_id: str
    risk_profile: str
    portfolio: PortfolioRepository
    research: ResearchRepository
    memory: MemoryRepository
    knowledge: KnowledgeRepository
    outbox: OutboxRepository


async def _market_quote(_: WebToolContext, args: MarketQuoteArgs) -> dict:
    return await asyncio.to_thread(get_realtime_price, args.code)


async def _market_history(_: WebToolContext, args: MarketHistoryArgs) -> dict:
    return await asyncio.to_thread(get_daily_price, args.code, args.days)


async def _portfolio_list(context: WebToolContext, _: EmptyArgs) -> dict:
    positions = await PortfolioService(context.portfolio).list_snapshots(context.user_id)
    return {
        "ok": True,
        "positions": jsonable_encoder(positions),
    }


async def _research_submit(context: WebToolContext, args: ResearchSubmitArgs) -> dict:
    job = await ResearchService(context.research, context.outbox).submit(
        user_id=context.user_id,
        stock_code=args.stock_code,
        depth=args.depth,
        risk_profile=args.risk_profile or context.risk_profile,
    )
    return {"ok": True, "job_id": job.id, "status": "queued", "stock_code": job.stock_code}


async def _memory_list(context: WebToolContext, _: EmptyArgs) -> dict:
    memories = await context.memory.list_memories(context.user_id, active_only=True)
    return {
        "ok": True,
        "memories": [
            {"type": item.memory_type, "key": item.memory_key, "value": item.memory_value}
            for item in memories
        ],
    }


async def _knowledge_search(context: WebToolContext, args: KnowledgeSearchArgs) -> dict:
    sources = await KnowledgeService(context.knowledge).search(
        user_id=context.user_id,
        question=args.question,
        stock_code=args.stock_code,
        source_types=args.source_types,
        top_k=args.top_k,
    )
    return {
        "ok": True,
        "sources": [item.model_dump() for item in sources],
        "instruction": "只能根据这些来源回答；材料不足时明确说明，并用 [1]、[2] 标注来源。",
    }


async def _not_executed(_: WebToolContext, __: BaseModel) -> dict:
    raise RuntimeError("confirmation tools are never executed directly")


def build_web_tool_registry() -> AsyncToolRegistry[WebToolContext]:
    return AsyncToolRegistry(
        [
            ToolSpec("market_quote", "查询一只 A 股的实时或最近价格。", MarketQuoteArgs, ToolEffect.READ, _market_quote),
            ToolSpec("market_history", "查询一只 A 股最近 5 至 90 个交易日的 OHLCV。", MarketHistoryArgs, ToolEffect.READ, _market_history),
            ToolSpec("portfolio_list", "读取当前登录用户的持仓。", EmptyArgs, ToolEffect.READ, _portfolio_list),
            ToolSpec("portfolio_upsert", "准备新增或更新持仓，必须由用户确认后才写入。", PortfolioUpsertArgs, ToolEffect.CONFIRM_WRITE, _not_executed),
            ToolSpec("research_submit", "创建一只股票的后台深度研究任务。", ResearchSubmitArgs, ToolEffect.BACKGROUND, _research_submit),
            ToolSpec("memory_list", "读取当前用户已保存的长期投资偏好和约束。", EmptyArgs, ToolEffect.READ, _memory_list),
            ToolSpec("memory_upsert", "准备保存明确的长期偏好或约束，必须由用户确认。", MemoryUpsertArgs, ToolEffect.CONFIRM_WRITE, _not_executed),
            ToolSpec(
                "knowledge_search",
                "检索当前用户上传并已索引的财报、公告、新闻、分析文章或个人笔记；可按股票代码和资料类型过滤。",
                KnowledgeSearchArgs,
                ToolEffect.READ,
                _knowledge_search,
            ),
        ]
    )
