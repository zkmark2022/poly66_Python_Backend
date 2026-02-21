from src.pm_common.errors import OrderLimitExceededError

MAX_ORDER_QUANTITY = 100_000


def check_order_limit(quantity: int) -> None:
    if not (1 <= quantity <= MAX_ORDER_QUANTITY):
        raise OrderLimitExceededError(f"quantity={quantity} must be in [1, {MAX_ORDER_QUANTITY}]")
