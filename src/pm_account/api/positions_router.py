# src/pm_account/api/positions_router.py
"""Positions REST API — 2 endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_account.application.positions_schemas import (
    PositionListResponse,
    PositionResponse,
)
from src.pm_account.infrastructure.positions_repository import PositionsRepository
from src.pm_common.database import get_db_session
from src.pm_common.errors import AppError
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel

router = APIRouter(prefix="/positions", tags=["positions"])
_repo = PositionsRepository()


@router.get("")
async def list_positions(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    items = await _repo.list_by_user(str(current_user.id), db)
    data = PositionListResponse(
        items=[PositionResponse(**p) for p in items],
        total=len(items),
    )
    return success_response(data.model_dump())


@router.get("/{market_id}")
async def get_position(
    market_id: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    pos = await _repo.get_by_market(str(current_user.id), market_id, db)
    if pos is None:
        raise AppError(3001, f"Position not found: {market_id}", http_status=404)
    return success_response(PositionResponse(**pos).model_dump())
