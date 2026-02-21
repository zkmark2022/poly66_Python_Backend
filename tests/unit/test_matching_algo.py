from datetime import UTC, datetime

from src.pm_matching.domain.models import BookOrder
from src.pm_matching.engine.matching_algo import match_order
from src.pm_matching.engine.order_book import OrderBook
from src.pm_order.domain.models import Order


def _order(user: str, side: str, direction: str, price: int,
           qty: int = 100, tif: str = "GTC") -> Order:
    from src.pm_order.domain.transformer import transform_order
    book_type, book_dir, book_price = transform_order(side, direction, price)
    return Order(id=f"o-{user}-{price}", client_order_id=f"c-{user}", market_id="mkt-1",
                 user_id=user, original_side=side, original_direction=direction,
                 original_price=price, book_type=book_type, book_direction=book_dir,
                 book_price=book_price, quantity=qty, time_in_force=tif, status="OPEN",
                 created_at=datetime.now(UTC))


def _resting(order_id: str, user: str, book_type: str, price: int, qty: int = 100) -> BookOrder:
    return BookOrder(order_id=order_id, user_id=user, book_type=book_type,
                     quantity=qty, created_at=datetime.now(UTC))


class TestMatchBuyOrder:
    def test_buy_yes_matches_sell_yes(self) -> None:
        # TRANSFER_YES scenario: Buy YES @65 taker, Sell YES @60 maker
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60)
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].price == 60        # maker price
        assert trades[0].quantity == 100
        assert trades[0].buy_book_type == "NATIVE_BUY"
        assert trades[0].sell_book_type == "NATIVE_SELL"

    def test_no_match_when_prices_do_not_cross(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 70)
        ob.add_order(maker, price=70, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65)
        trades = match_order(incoming, ob)
        assert len(trades) == 0
        assert incoming.remaining_quantity == 100  # untouched

    def test_self_trade_is_skipped(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-A", "NATIVE_SELL", 60)  # same user!
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65)
        trades = match_order(incoming, ob)
        assert len(trades) == 0  # skipped, not rejected

    def test_partial_fill_updates_remaining(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60, qty=50)
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65, qty=100)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].quantity == 50
        assert incoming.remaining_quantity == 50
        assert incoming.filled_quantity == 50

    def test_buy_no_mint_scenario(self) -> None:
        # Buy NO @35 → SYNTHETIC_SELL @65; Buy YES @65 maker
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_BUY", 65)
        ob.add_order(maker, price=65, side="BUY")
        # incoming: Buy NO @35 → SYNTHETIC_SELL @65
        incoming = _order("user-A", "NO", "BUY", 35)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].buy_book_type == "NATIVE_BUY"
        assert trades[0].sell_book_type == "SYNTHETIC_SELL"


class TestMatchSellOrder:
    def test_sell_yes_matches_buy_yes(self) -> None:
        # TRANSFER_YES: Sell YES @60 taker, Buy YES @65 maker
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_BUY", 65)
        ob.add_order(maker, price=65, side="BUY")
        incoming = _order("user-A", "YES", "SELL", 60)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].price == 65  # maker price

    def test_ioc_cancel_remainder(self) -> None:
        # IOC: partial fill, remainder should be 50 (caller handles cancel)
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60, qty=50)
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65, qty=100, tif="IOC")
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].quantity == 50
        assert incoming.remaining_quantity == 50
        # IOC cancel is handled by MatchingEngine caller, not match_order

    def test_time_priority_two_makers(self) -> None:
        # Both at price 60; maker-1 added first, should fill first
        ob = OrderBook(market_id="mkt-1")
        maker1 = _resting("maker-1", "user-B", "NATIVE_SELL", 60, qty=50)
        maker2 = _resting("maker-2", "user-C", "NATIVE_SELL", 60, qty=50)
        ob.add_order(maker1, price=60, side="SELL")
        ob.add_order(maker2, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65, qty=50)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].sell_order_id == "maker-1"  # time priority

    def test_multi_fill_from_one_incoming(self) -> None:
        # Incoming 200 qty, fills against 2 makers of 100 each
        ob = OrderBook(market_id="mkt-1")
        maker1 = _resting("maker-1", "user-B", "NATIVE_SELL", 60, qty=100)
        maker2 = _resting("maker-2", "user-C", "NATIVE_SELL", 60, qty=100)
        ob.add_order(maker1, price=60, side="SELL")
        ob.add_order(maker2, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65, qty=200)
        trades = match_order(incoming, ob)
        assert len(trades) == 2
        assert incoming.remaining_quantity == 0
        assert incoming.status == "FILLED"

    def test_boundary_price_99(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 99)
        ob.add_order(maker, price=99, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 99)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].price == 99

    def test_add_to_empty_book(self) -> None:
        # No resting orders, incoming gets no fills
        ob = OrderBook(market_id="mkt-1")
        incoming = _order("user-A", "YES", "BUY", 65)
        trades = match_order(incoming, ob)
        assert len(trades) == 0
        assert incoming.remaining_quantity == 100

    def test_price_improvement_taker_gets_better_price(self) -> None:
        # Taker bid @70, maker ask @60 → fill at maker price 60
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60)
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 70)  # willing to pay 70
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].price == 60  # gets maker price, not taker price

    def test_sell_no_burn_scenario(self) -> None:
        # Sell YES @60 maker, Sell NO @40 → SYNTHETIC_BUY @60 taker
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60)
        ob.add_order(maker, price=60, side="SELL")
        # incoming: Sell NO @40 → SYNTHETIC_BUY @60
        incoming = _order("user-A", "NO", "SELL", 40)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].buy_book_type == "SYNTHETIC_BUY"
        assert trades[0].sell_book_type == "NATIVE_SELL"

    def test_transfer_no_scenario(self) -> None:
        # Buy NO @35 → SYNTHETIC_SELL @65, Sell NO @30 → SYNTHETIC_BUY @70 maker
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "SYNTHETIC_BUY", 70)
        ob.add_order(maker, price=70, side="BUY")
        incoming = _order("user-A", "NO", "BUY", 35)  # SYNTHETIC_SELL @65
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].buy_book_type == "SYNTHETIC_BUY"
        assert trades[0].sell_book_type == "SYNTHETIC_SELL"

    def test_self_trade_with_second_maker_fills(self) -> None:
        # First maker is same user (skip), second maker is different user (fill)
        ob = OrderBook(market_id="mkt-1")
        self_maker = _resting("maker-self", "user-A", "NATIVE_SELL", 60, qty=50)
        other_maker = _resting("maker-other", "user-B", "NATIVE_SELL", 60, qty=50)
        ob.add_order(self_maker, price=60, side="SELL")
        ob.add_order(other_maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65)
        trades = match_order(incoming, ob)
        assert len(trades) == 1
        assert trades[0].sell_order_id == "maker-other"

    def test_gtc_partial_fill_status(self) -> None:
        ob = OrderBook(market_id="mkt-1")
        maker = _resting("maker-1", "user-B", "NATIVE_SELL", 60, qty=40)
        ob.add_order(maker, price=60, side="SELL")
        incoming = _order("user-A", "YES", "BUY", 65, qty=100, tif="GTC")
        match_order(incoming, ob)
        assert incoming.status == "PARTIALLY_FILLED"
        assert incoming.remaining_quantity == 60
