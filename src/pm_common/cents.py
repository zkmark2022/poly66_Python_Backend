"""Integer arithmetic utilities for cents-based prediction market.

All prices, amounts, and balances use int (cents). No float, no Decimal.
Ref: Planning/Detail_Design/01_全局约定与数据库设计.md §1.1
"""


def validate_price(price: int) -> None:
    """Validate that price is in the range [1, 99] cents."""
    if not (1 <= price <= 99):
        raise ValueError(f"Price must be between 1 and 99 cents, got {price}")


def cents_to_display(cents: int) -> str:
    """Convert cents to display string: 6500 -> '$65.00', -1200 -> '-$12.00'."""
    if cents < 0:
        abs_cents = -cents
        return f"-${abs_cents // 100:,}.{abs_cents % 100:02d}"
    return f"${cents // 100:,}.{cents % 100:02d}"


def calculate_fee(trade_value: int, fee_rate_bps: int) -> int:
    """Calculate fee with ceiling division (platform never loses).

    fee = ceil(trade_value * fee_rate_bps / 10000)
    Using integer ceiling: (a + b - 1) // b
    """
    if trade_value == 0 or fee_rate_bps == 0:
        return 0
    return (trade_value * fee_rate_bps + 9999) // 10000
