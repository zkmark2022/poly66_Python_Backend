import pytest

from src.pm_order.domain.transformer import transform_order


@pytest.mark.parametrize("side,direction,price,exp_type,exp_dir,exp_price", [
    ("YES", "BUY",  65, "NATIVE_BUY",     "BUY",  65),
    ("YES", "SELL", 67, "NATIVE_SELL",    "SELL", 67),
    ("NO",  "BUY",  35, "SYNTHETIC_SELL", "SELL", 65),  # 100-35=65
    ("NO",  "SELL", 40, "SYNTHETIC_BUY",  "BUY",  60),  # 100-40=60
    ("NO",  "BUY",   1, "SYNTHETIC_SELL", "SELL", 99),  # boundary
    ("NO",  "BUY",  99, "SYNTHETIC_SELL", "SELL",  1),  # boundary
    ("NO",  "SELL",  1, "SYNTHETIC_BUY",  "BUY",  99),  # boundary
    ("NO",  "SELL", 99, "SYNTHETIC_BUY",  "BUY",   1),  # boundary
])
def test_transform_order(
    side: str, direction: str, price: int,
    exp_type: str, exp_dir: str, exp_price: int,
) -> None:
    book_type, book_dir, book_price = transform_order(side, direction, price)
    assert book_type == exp_type
    assert book_dir == exp_dir
    assert book_price == exp_price
