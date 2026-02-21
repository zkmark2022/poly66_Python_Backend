# src/pm_order/application/service.py
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.datetime_utils import utc_now
from src.pm_common.errors import AppError, DuplicateOrderError
from src.pm_common.id_generator import generate_id
from src.pm_matching.application.service import get_matching_engine
from src.pm_matching.domain.models import TradeResult
from src.pm_order.application.schemas import (
    CancelOrderResponse,
    OrderListResponse,
    OrderResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
    TradeResponse,
)
from src.pm_order.domain.models import Order
from src.pm_order.infrastructure.persistence import OrderRepository

_repo = OrderRepository()


def _order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        client_order_id=order.client_order_id,
        market_id=order.market_id,
        side=order.original_side,
        direction=order.original_direction,
        price_cents=order.original_price,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        remaining_quantity=order.remaining_quantity,
        status=order.status,
        time_in_force=order.time_in_force,
    )


def _trade_to_response(trade: TradeResult) -> TradeResponse:
    scenario = f"{trade.buy_book_type}_vs_{trade.sell_book_type}"
    return TradeResponse(
        buy_order_id=trade.buy_order_id,
        sell_order_id=trade.sell_order_id,
        price=trade.price,
        quantity=trade.quantity,
        scenario=scenario,
    )


def _build_place_response(
    order: Order, trades: list[TradeResult], netting: dict[str, int] | None
) -> PlaceOrderResponse:
    return PlaceOrderResponse(
        order=_order_to_response(order),
        trades=[_trade_to_response(t) for t in trades],
        netting_result=netting,
    )


async def place_order(
    req: PlaceOrderRequest, user_id: str, db: AsyncSession
) -> PlaceOrderResponse:
    # Idempotency check
    existing = await _repo.get_by_client_order_id(req.client_order_id, user_id, db)
    if existing:
        if (
            existing.original_side != req.side
            or existing.original_direction != req.direction
            or existing.original_price != req.price_cents
            or existing.quantity != req.quantity
        ):
            raise DuplicateOrderError(req.client_order_id)
        return _build_place_response(existing, [], None)

    order = Order(
        id=generate_id(),
        client_order_id=req.client_order_id,
        market_id=req.market_id,
        user_id=user_id,
        original_side=req.side,
        original_direction=req.direction,
        original_price=req.price_cents,
        book_type="",
        book_direction="",
        book_price=0,
        quantity=req.quantity,
        time_in_force=req.time_in_force,
        status="OPEN",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    engine = get_matching_engine()
    order, trades, netting_qty = await engine.place_order(order, _repo, db)
    netting: dict[str, int] | None = (
        {"netting_qty": netting_qty, "refund_amount": netting_qty * 100} if netting_qty else None
    )
    return _build_place_response(order, trades, netting)


async def cancel_order(
    order_id: str, user_id: str, db: AsyncSession
) -> CancelOrderResponse:
    engine = get_matching_engine()
    order = await engine.cancel_order(order_id, user_id, _repo, db)
    return CancelOrderResponse(
        order_id=order.id,
        unfrozen_amount=order.frozen_amount,
        unfrozen_asset_type=order.frozen_asset_type,
    )


async def get_order(
    order_id: str, user_id: str, db: AsyncSession
) -> OrderResponse:
    order = await _repo.get_by_id(order_id, db)
    if order is None:
        raise AppError(4004, "Order not found", http_status=404)
    if order.user_id != user_id:
        raise AppError(403, "Forbidden", http_status=403)
    return _order_to_response(order)


async def list_orders(
    user_id: str,
    market_id: str | None,
    status: str | None,
    limit: int,
    cursor: str | None,
    db: AsyncSession,
) -> OrderListResponse:
    statuses = [status] if status else None
    orders = await _repo.list_by_user(
        user_id=user_id,
        market_id=market_id,
        statuses=statuses,
        limit=limit + 1,
        cursor_id=cursor,
        db=db,
    )
    has_more = len(orders) > limit
    if has_more:
        orders = orders[:limit]
    next_cursor = orders[-1].id if has_more else None
    return OrderListResponse(
        orders=[_order_to_response(o) for o in orders],
        next_cursor=next_cursor,
    )
