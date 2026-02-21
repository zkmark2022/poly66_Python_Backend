from datetime import UTC, datetime

from src.pm_matching.domain.models import BookOrder
from src.pm_matching.engine.order_book import OrderBook


def _bo(
    order_id: str,
    user_id: str = "u1",
    book_type: str = "NATIVE_BUY",
    qty: int = 100,
) -> BookOrder:
    return BookOrder(
        order_id=order_id,
        user_id=user_id,
        book_type=book_type,
        quantity=qty,
        created_at=datetime.now(UTC),
    )


class TestOrderBookBids:
    def test_add_bid_updates_best_bid(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1"), price=65, side="BUY")
        assert ob.best_bid == 65

    def test_best_bid_is_highest_of_multiple(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1"), price=60, side="BUY")
        ob.add_order(_bo("o2"), price=65, side="BUY")
        assert ob.best_bid == 65

    def test_empty_book_best_bid_zero(self) -> None:
        assert OrderBook(market_id="m").best_bid == 0


class TestOrderBookAsks:
    def test_add_ask_updates_best_ask(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1", book_type="NATIVE_SELL"), price=70, side="SELL")
        assert ob.best_ask == 70

    def test_best_ask_is_lowest_of_multiple(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1", book_type="NATIVE_SELL"), price=70, side="SELL")
        ob.add_order(_bo("o2", book_type="NATIVE_SELL"), price=65, side="SELL")
        assert ob.best_ask == 65

    def test_empty_book_best_ask_100(self) -> None:
        assert OrderBook(market_id="m").best_ask == 100


class TestOrderBookCancel:
    def test_cancel_removes_from_index(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1"), price=65, side="BUY")
        ob.cancel_order("o1")
        assert "o1" not in ob._order_index

    def test_cancel_sole_bid_resets_best_bid(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.add_order(_bo("o1"), price=65, side="BUY")
        ob.cancel_order("o1")
        assert ob.best_bid == 0

    def test_cancel_nonexistent_is_noop(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        ob.cancel_order("ghost")  # must not raise
