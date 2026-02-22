# src/pm_clearing/domain/global_invariants.py
"""Global zero-sum invariant check (INV-G)."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_USER_BALANCE_SQL = text("""
    SELECT COALESCE(SUM(available_balance + frozen_balance), 0)
    FROM accounts
    WHERE user_id NOT IN ('SYSTEM_RESERVE', 'PLATFORM_FEE')
""")
_MARKET_RESERVE_SQL = text(
    "SELECT COALESCE(SUM(reserve_balance), 0) FROM markets"
)
_PLATFORM_FEE_SQL = text(
    "SELECT COALESCE(available_balance, 0) FROM accounts WHERE user_id = 'PLATFORM_FEE'"
)
_NET_DEPOSIT_SQL = text("""
    SELECT COALESCE(SUM(amount), 0)
    FROM ledger_entries
    WHERE entry_type IN ('DEPOSIT', 'WITHDRAW')
""")


async def verify_global_invariants(db: AsyncSession) -> list[str]:
    """Check INV-G: total assets == net deposits. Returns list of violation strings."""
    violations: list[str] = []
    user_bal = (await db.execute(_USER_BALANCE_SQL)).scalar_one()
    market_reserve = (await db.execute(_MARKET_RESERVE_SQL)).scalar_one()
    platform_fee = (await db.execute(_PLATFORM_FEE_SQL)).scalar_one()
    net_deposits = (await db.execute(_NET_DEPOSIT_SQL)).scalar_one()

    total_assets = user_bal + market_reserve + platform_fee
    if total_assets != net_deposits:
        msg = (
            f"INV-G violated: user_balances({user_bal}) + "
            f"market_reserves({market_reserve}) + platform_fee({platform_fee}) "
            f"= {total_assets} != net_deposits={net_deposits}"
        )
        violations.append(msg)
        logger.error(msg)
    return violations
