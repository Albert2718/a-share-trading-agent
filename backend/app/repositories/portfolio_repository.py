from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Portfolio, Position


class PortfolioRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_default(self, user_id: str) -> Portfolio:
        portfolio = await self.session.scalar(
            select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.created_at).limit(1)
        )
        if portfolio is None:
            portfolio = Portfolio(user_id=user_id)
            self.session.add(portfolio)
            await self.session.flush()
        return portfolio

    async def list_positions(self, user_id: str) -> list[Position]:
        rows = await self.session.scalars(
            select(Position)
            .join(Portfolio)
            .where(Portfolio.user_id == user_id)
            .order_by(Position.stock_code)
        )
        return list(rows)

    async def upsert_position(self, *, portfolio: Portfolio, stock_code: str, stock_name: str, quantity: int, average_cost):
        position = await self.session.scalar(
            select(Position).where(Position.portfolio_id == portfolio.id, Position.stock_code == stock_code)
        )
        if position is None:
            position = Position(
                portfolio_id=portfolio.id,
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                average_cost=average_cost,
            )
            self.session.add(position)
        else:
            position.stock_name = stock_name or position.stock_name
            position.quantity = quantity
            position.average_cost = average_cost
        await self.session.flush()
        return position
