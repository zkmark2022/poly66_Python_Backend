"""Order transformation layer: maps user intent (YES/NO BUY/SELL) to single YES orderbook view."""


def transform_order(side: str, direction: str, price: int) -> tuple[str, str, int]:
    """
    Transform user intent into orderbook representation.

    Returns: (book_type, book_direction, book_price)
    - YES BUY  → NATIVE_BUY,     BUY,  price
    - YES SELL → NATIVE_SELL,    SELL, price
    - NO  BUY  → SYNTHETIC_SELL, SELL, 100 - price
    - NO  SELL → SYNTHETIC_BUY,  BUY,  100 - price
    """
    if side == "YES":
        if direction == "BUY":
            return ("NATIVE_BUY", "BUY", price)
        return ("NATIVE_SELL", "SELL", price)
    # NO side
    if direction == "BUY":
        return ("SYNTHETIC_SELL", "SELL", 100 - price)
    return ("SYNTHETIC_BUY", "BUY", 100 - price)
