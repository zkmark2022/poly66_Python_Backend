from datetime import UTC, datetime
from typing import Any

from src.pm_order.domain.models import Order


def _make_order(**kwargs: Any) -> Order:
    defaults: dict[str, Any] = dict(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        client_order_id="client-1",
        market_id="mkt-1",
        user_id="user-1",
        original_side="YES",
        original_direction="BUY",
        original_price=65,
        book_type="NATIVE_BUY",
        book_direction="BUY",
        book_price=65,
        quantity=100,
        frozen_amount=6600,
        frozen_asset_type="FUNDS",
        time_in_force="GTC",
        status="OPEN",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return Order(**defaults)


class TestOrderModel:
    def test_initial_remaining_quantity(self) -> None:
        order = _make_order(quantity=100)
        assert order.remaining_quantity == 100

    def test_is_active_open(self) -> None:
        order = _make_order(status="OPEN")
        assert order.is_active is True

    def test_is_active_partially_filled(self) -> None:
        order = _make_order(status="PARTIALLY_FILLED")
        assert order.is_active is True

    def test_is_active_filled(self) -> None:
        order = _make_order(status="FILLED")
        assert order.is_active is False

    def test_is_cancellable(self) -> None:
        order = _make_order(status="OPEN")
        assert order.is_cancellable is True

    def test_is_not_cancellable_filled(self) -> None:
        order = _make_order(status="FILLED")
        assert order.is_cancellable is False
