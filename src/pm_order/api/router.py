# src/pm_order/api/router.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.database import get_db_session
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel
from src.pm_order.application import service as svc
from src.pm_order.application.schemas import (
    CancelOrderResponse,
    OrderListResponse,
    OrderResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=PlaceOrderResponse, status_code=201)
async def place_order(
    req: PlaceOrderRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PlaceOrderResponse:
    return await svc.place_order(req, str(current_user.id), db)


@router.post("/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(
    order_id: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CancelOrderResponse:
    return await svc.cancel_order(order_id, str(current_user.id), db)


@router.get("", response_model=OrderListResponse)
async def list_orders(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    market_id: str | None = Query(None, description="Filter by market ID"),
    status: str | None = Query(None, description="Filter by order status"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    cursor: str | None = Query(None, description="Pagination cursor (order ID)"),
) -> OrderListResponse:
    return await svc.list_orders(str(current_user.id), market_id, status, limit, cursor, db)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderResponse:
    return await svc.get_order(order_id, str(current_user.id), db)
