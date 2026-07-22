from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from app.repositories.portfolio_repository import PortfolioRepository
from src.tools.market import get_realtime_price


class PortfolioService:
    """Combine persisted positions with ephemeral market quotes and P&L."""

    def __init__(
        self,
        repository: PortfolioRepository,
        quote_loader: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.repository = repository
        self.quote_loader = quote_loader or get_realtime_price

    async def list_snapshots(
        self,
        user_id: str,
        *,
        refresh_market: bool = True,
    ) -> list[dict[str, Any]]:
        positions = await self.repository.list_positions(user_id)
        if not refresh_market:
            return [self._snapshot(item, None) for item in positions]
        semaphore = asyncio.Semaphore(5)

        async def load(position):
            async with semaphore:
                try:
                    quote = await asyncio.to_thread(
                        self.quote_loader, position.stock_code
                    )
                except Exception:
                    quote = {"ok": False, "error": "market data unavailable"}
                return self._snapshot(position, quote)

        return list(await asyncio.gather(*(load(item) for item in positions)))

    @staticmethod
    def _snapshot(position, quote: dict[str, Any] | None) -> dict[str, Any]:
        average_cost = Decimal(str(position.average_cost))
        quantity = position.quantity
        cost_value = average_cost * quantity
        price_value = (quote or {}).get("latest_price")
        try:
            market_price = Decimal(str(price_value)) if price_value is not None else None
        except (ValueError, ArithmeticError):
            market_price = None
        market_value = market_price * quantity if market_price is not None else None
        unrealized_pnl = market_value - cost_value if market_value is not None else None
        pnl_pct = (
            unrealized_pnl / cost_value * 100
            if unrealized_pnl is not None and cost_value != 0
            else None
        )
        return {
            "id": position.id,
            "stock_code": position.stock_code,
            "stock_name": position.stock_name or str((quote or {}).get("name") or ""),
            "quantity": quantity,
            "average_cost": average_cost,
            "cost_value": cost_value,
            "market_price": market_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "quote_time": str((quote or {}).get("quote_time") or "") or None,
            "is_realtime": bool((quote or {}).get("is_realtime")),
            "market_source": str((quote or {}).get("source") or "") or None,
            "market_error": (
                None
                if market_price is not None
                else str((quote or {}).get("error") or "market data not refreshed")
            ),
        }
