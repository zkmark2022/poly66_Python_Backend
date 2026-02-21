"""pm_market REST endpoints.

GET /markets                          — list with cursor pagination
GET /markets/{market_id}              — full detail
GET /markets/{market_id}/orderbook    — order book snapshot (DB aggregated)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel
from src.pm_market.application.service import MarketApplicationService

router = APIRouter(prefix="/markets", tags=["markets"])

_service = MarketApplicationService()


@router.get("")
async def list_markets(
    request: Request,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(
        None, description="Filter by status. Default: ACTIVE. Use ALL for no filter."
    ),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
) -> ApiResponse:
    result = await _service.list_markets(db, status, category, cursor, limit)
    resp = success_response(result.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp


@router.get("/{market_id}")
async def get_market(
    market_id: str,
    request: Request,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    result = await _service.get_market(db, market_id)
    resp = success_response(result.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp


@router.get("/{market_id}/orderbook")
async def get_orderbook(
    market_id: str,
    request: Request,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    levels: int = Query(10, ge=1, le=99),
) -> ApiResponse:
    result = await _service.get_orderbook(db, market_id, levels)
    resp = success_response(result.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp
