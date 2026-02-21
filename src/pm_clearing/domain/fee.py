"""Fee calculation — distinguishes NATIVE vs SYNTHETIC for fee base."""


def get_fee_trade_value(
    book_type: str, trade_price: int, quantity: int, buy_original_price: int
) -> int:
    """Return the trade value used as fee base.

    NATIVE orders: YES price x qty.
    SYNTHETIC_SELL (Buy NO): NO price x qty (buy_original_price).
    SYNTHETIC_BUY (Sell NO): (100 - trade_price) x qty = NO price.
    """
    if book_type in ("NATIVE_BUY", "NATIVE_SELL"):
        return trade_price * quantity
    if book_type == "SYNTHETIC_SELL":
        return buy_original_price * quantity  # NO price stored in TradeResult
    # SYNTHETIC_BUY
    return (100 - trade_price) * quantity  # NO price = 100 - YES trade price


def calc_fee(trade_value: int, fee_bps: int) -> int:
    """Ceiling division fee: (trade_value x fee_bps + 9999) // 10000."""
    return (trade_value * fee_bps + 9999) // 10000
