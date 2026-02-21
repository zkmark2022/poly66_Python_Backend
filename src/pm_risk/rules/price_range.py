from src.pm_common.errors import AppError


def check_price_range(price: int) -> None:
    """Raise AppError(4001) if price is not in [1, 99]."""
    if not (1 <= price <= 99):
        raise AppError(4001, f"Price {price} out of range [1, 99]", http_status=400)
