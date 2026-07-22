from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser, DbSession
from app.repositories.portfolio_repository import PortfolioRepository
from app.schemas.portfolio import PositionCreate, PositionResponse, PositionSnapshotResponse
from app.services.portfolio_service import PortfolioService


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/positions", response_model=list[PositionSnapshotResponse])
async def list_positions(
    current_user: CurrentUser,
    session: DbSession,
    refresh_market: bool = True,
):
    return await PortfolioService(PortfolioRepository(session)).list_snapshots(
        current_user.id,
        refresh_market=refresh_market,
    )


@router.put("/positions/{stock_code}", response_model=PositionResponse)
async def put_position(
    stock_code: str,
    payload: PositionCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    if stock_code != payload.stock_code:
        raise HTTPException(status_code=400, detail="路径中的股票代码与请求内容不一致")
    repository = PortfolioRepository(session)
    portfolio = await repository.get_default(current_user.id)
    position = await repository.upsert_position(
        portfolio=portfolio,
        stock_code=stock_code,
        stock_name=payload.stock_name,
        quantity=payload.quantity,
        average_cost=payload.average_cost,
    )
    return PositionResponse.model_validate(position)
