from src.pm_common.errors import AppError

MAX_ORDER_QUANTITY = 100_000


def check_order_limit(quantity: int) -> None:
    """Raise AppError(4002) if quantity is not in [1, MAX_ORDER_QUANTITY]."""
    if not (1 <= quantity <= MAX_ORDER_QUANTITY):
        raise AppError(
            4002,
            f"Quantity {quantity} must be in [1, {MAX_ORDER_QUANTITY}]",
            http_status=400,
        )
