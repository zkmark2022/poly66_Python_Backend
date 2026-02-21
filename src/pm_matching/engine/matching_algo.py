"""Price-time priority matching algorithm for the single YES orderbook."""
from src.pm_matching.domain.models import BookOrder, TradeResult
from src.pm_matching.engine.order_book import OrderBook
from src.pm_order.domain.models import Order
from src.pm_risk.rules.self_trade import is_self_trade


def match_order(incoming: Order, ob: OrderBook) -> list[TradeResult]:
    if incoming.book_direction == "BUY":
        return _match_buy(incoming, ob)
    return _match_sell(incoming, ob)


def _match_buy(incoming: Order, ob: OrderBook) -> list[TradeResult]:
    """Match a BUY order against resting asks (price-time priority)."""
    trades: list[TradeResult] = []
    while incoming.remaining_quantity > 0 and ob.best_ask <= incoming.book_price:
        price = ob.best_ask
        queue = ob.asks[price]
        # track how many items we've checked at this price level
        checked = 0
        total = len(queue)
        while queue and incoming.remaining_quantity > 0 and checked < total:
            resting: BookOrder = queue[0]
            if is_self_trade(incoming.user_id, resting.user_id):
                queue.rotate(-1)
                checked += 1
                continue
            fill_qty = min(incoming.remaining_quantity, resting.quantity)
            trades.append(_make_trade_buy_incoming(incoming, resting, price, fill_qty))
            _apply_fill(incoming, resting, fill_qty)
            if resting.quantity == 0:
                queue.popleft()
                ob._order_index.pop(resting.order_id, None)
                total -= 1
            else:
                # resting still has quantity (incoming fully filled)
                break
        if not queue:
            ob._refresh_best_ask()
            if ob.best_ask > incoming.book_price:
                break
        else:
            # either all remaining are self-trades, or incoming is filled
            break
    return trades


def _match_sell(incoming: Order, ob: OrderBook) -> list[TradeResult]:
    """Match a SELL order against resting bids (price-time priority)."""
    trades: list[TradeResult] = []
    while incoming.remaining_quantity > 0 and ob.best_bid >= incoming.book_price:
        price = ob.best_bid
        queue = ob.bids[price]
        checked = 0
        total = len(queue)
        while queue and incoming.remaining_quantity > 0 and checked < total:
            resting: BookOrder = queue[0]
            if is_self_trade(incoming.user_id, resting.user_id):
                queue.rotate(-1)
                checked += 1
                continue
            fill_qty = min(incoming.remaining_quantity, resting.quantity)
            trades.append(_make_trade_sell_incoming(incoming, resting, price, fill_qty))
            _apply_fill(incoming, resting, fill_qty)
            if resting.quantity == 0:
                queue.popleft()
                ob._order_index.pop(resting.order_id, None)
                total -= 1
            else:
                # resting still has quantity (incoming fully filled)
                break
        if not queue:
            ob._refresh_best_bid()
            if ob.best_bid < incoming.book_price:
                break
        else:
            # either all remaining are self-trades, or incoming is filled
            break
    return trades


def _make_trade_buy_incoming(
    buy_incoming: Order, sell_resting: BookOrder, price: int, qty: int
) -> TradeResult:
    """incoming is BUY, resting is SELL."""
    return TradeResult(
        buy_order_id=buy_incoming.id,
        sell_order_id=sell_resting.order_id,
        buy_user_id=buy_incoming.user_id,
        sell_user_id=sell_resting.user_id,
        market_id=buy_incoming.market_id,
        price=price,
        quantity=qty,
        buy_book_type=buy_incoming.book_type,
        sell_book_type=sell_resting.book_type,
        buy_original_price=buy_incoming.original_price,
        maker_order_id=sell_resting.order_id,  # resting = maker
        taker_order_id=buy_incoming.id,
    )


def _make_trade_sell_incoming(
    sell_incoming: Order, buy_resting: BookOrder, price: int, qty: int
) -> TradeResult:
    """incoming is SELL, resting is BUY."""
    return TradeResult(
        buy_order_id=buy_resting.order_id,
        sell_order_id=sell_incoming.id,
        buy_user_id=buy_resting.user_id,
        sell_user_id=sell_incoming.user_id,
        market_id=sell_incoming.market_id,
        price=price,
        quantity=qty,
        buy_book_type=buy_resting.book_type,
        sell_book_type=sell_incoming.book_type,
        buy_original_price=0,  # resting BUY: original_price not tracked in BookOrder
        maker_order_id=buy_resting.order_id,  # resting = maker
        taker_order_id=sell_incoming.id,
    )


def _apply_fill(incoming: Order, resting: BookOrder, qty: int) -> None:
    incoming.filled_quantity += qty
    incoming.remaining_quantity -= qty
    resting.quantity -= qty
    if incoming.remaining_quantity == 0:
        incoming.status = "FILLED"
    else:
        incoming.status = "PARTIALLY_FILLED"
