from collections import deque
from dataclasses import dataclass, field

from src.pm_matching.domain.models import BookOrder


@dataclass
class OrderBook:
    """Single YES orderbook per prediction market. Indices 1-99 = price cents."""

    market_id: str
    bids: list[deque[BookOrder]] = field(default_factory=lambda: [deque() for _ in range(100)])
    asks: list[deque[BookOrder]] = field(default_factory=lambda: [deque() for _ in range(100)])
    best_bid: int = 0  # 0 = no bids
    best_ask: int = 100  # 100 = no asks
    _order_index: dict[str, tuple[str, int]] = field(default_factory=dict)
    # _order_index[order_id] = (side, price)

    def add_order(self, book_order: BookOrder, price: int, side: str) -> None:
        if side == "BUY":
            self.bids[price].append(book_order)
            if price > self.best_bid:
                self.best_bid = price
        else:
            self.asks[price].append(book_order)
            if price < self.best_ask:
                self.best_ask = price
        self._order_index[book_order.order_id] = (side, price)

    def cancel_order(self, order_id: str) -> None:
        if order_id not in self._order_index:
            return
        side, price = self._order_index.pop(order_id)
        queue = self.bids[price] if side == "BUY" else self.asks[price]
        for i, bo in enumerate(queue):
            if bo.order_id == order_id:
                del queue[i]
                break
        if side == "BUY" and price == self.best_bid:
            self._refresh_best_bid()
        elif side == "SELL" and price == self.best_ask:
            self._refresh_best_ask()

    def _refresh_best_bid(self) -> None:
        for p in range(99, 0, -1):
            if self.bids[p]:
                self.best_bid = p
                return
        self.best_bid = 0

    def _refresh_best_ask(self) -> None:
        for p in range(1, 100):
            if self.asks[p]:
                self.best_ask = p
                return
        self.best_ask = 100
