from src.pm_common.errors import PriceOutOfRangeError


def check_price_range(price: int) -> None:
    if not (1 <= price <= 99):
        raise PriceOutOfRangeError(price)
