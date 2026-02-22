# src/pm_clearing/api/trades_router.py
"""Trades REST API."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.application.trades_schemas import TradeListResponse, TradeResponse
from src.pm_clearing.infrastructure.trades_repository import TradesRepository
from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel

router = APIRouter(prefix="/trades", tags=["trades"])
_repo = TradesRepository()


@router.get("")
async def list_trades(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    market_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
) -> ApiResponse:
    items = await _repo.list_by_user(str(current_user.id), market_id, limit + 1, cursor, db)
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    next_cursor = items[-1]["trade_id"] if has_more and items else None
    data = TradeListResponse(
        items=[TradeResponse(**t) for t in items],
        has_more=has_more,
        next_cursor=next_cursor,
    )
    return success_response(data.model_dump())
