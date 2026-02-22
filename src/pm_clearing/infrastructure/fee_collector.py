"""Taker fee collection — debit taker, credit PLATFORM_FEE account."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PLATFORM_FEE_USER_ID = "PLATFORM_FEE"

_DEDUCT_FROZEN_SQL = text("""
    UPDATE accounts
    SET frozen_balance    = frozen_balance    - :actual_fee,
        available_balance = available_balance + :refund,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")

_DEDUCT_AVAILABLE_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance - :actual_fee,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")

_CREDIT_PLATFORM_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")


async def collect_fee_from_frozen(
    taker_user_id: str,
    actual_fee: int,
    max_fee: int,
    db: AsyncSession,
) -> None:
    """Collect fee from pre-frozen funds buffer (NATIVE_BUY or SYNTHETIC_SELL taker)."""
    refund = max_fee - actual_fee
    await db.execute(
        _DEDUCT_FROZEN_SQL,
        {"user_id": taker_user_id, "actual_fee": actual_fee, "refund": refund},
    )
    await db.execute(
        _CREDIT_PLATFORM_SQL,
        {"user_id": PLATFORM_FEE_USER_ID, "amount": actual_fee},
    )


async def collect_fee_from_proceeds(
    taker_user_id: str,
    actual_fee: int,
    db: AsyncSession,
) -> None:
    """Collect fee from proceeds (NATIVE_SELL or SYNTHETIC_BUY taker)."""
    await db.execute(
        _DEDUCT_AVAILABLE_SQL,
        {"user_id": taker_user_id, "actual_fee": actual_fee},
    )
    await db.execute(
        _CREDIT_PLATFORM_SQL,
        {"user_id": PLATFORM_FEE_USER_ID, "amount": actual_fee},
    )
