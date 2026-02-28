"""Privileged Burn (Auto-Merge) — AMM destroys YES+NO share pairs, recovers cash.

Aligned with interface contract v1.4 §3.4:
- Validates sufficient available inventory (volume - pending_sell)
- Deducts YES and NO positions
- Releases cost_sum proportionally (weighted average)
- Reduces market reserve_balance
- Credits AMM account available_balance
- Writes ledger entries (BURN_REVENUE + BURN_RESERVE_OUT)
- Writes audit trade record (scenario=BURN)
- Idempotent via idempotency_key
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.errors import AppError

logger = logging.getLogger(__name__)

RECOVERY_PER_SHARE_CENTS = 100


async def execute_privileged_burn(
    user_id: str,
    market_id: str,
    quantity: int,
    idempotency_key: str,
    db: AsyncSession,
) -> dict:
    """Execute privileged burn within the caller's transaction."""
    # Step 1: Idempotency check
    existing = await db.execute(
        text(
            "SELECT amount_cents, reference_id FROM ledger_entries "
            "WHERE reference_type = 'AMM_BURN' AND reference_id = :key"
        ),
        {"key": idempotency_key},
    )
    if existing.fetchone() is not None:
        logger.info("Burn idempotency hit: key=%s", idempotency_key)
        return {"idempotent_hit": True, "idempotency_key": idempotency_key}

    # Step 2: Validate market
    market_result = await db.execute(
        text("SELECT status FROM markets WHERE id = :mid"),
        {"mid": market_id},
    )
    market_row = market_result.fetchone()
    if market_row is None:
        raise AppError(3001, "Market not found", http_status=404)
    if market_row.status != "ACTIVE":
        raise AppError(3002, "Market is not active", http_status=422)

    # Step 3: Validate positions (available = volume - pending_sell)
    pos_result = await db.execute(
        text(
            "SELECT yes_volume, no_volume, yes_pending_sell, no_pending_sell, "
            "yes_cost_sum, no_cost_sum "
            "FROM positions WHERE user_id = :uid AND market_id = :mid FOR UPDATE"
        ),
        {"uid": user_id, "mid": market_id},
    )
    pos_row = pos_result.fetchone()
    if pos_row is None:
        raise AppError(5001, "No positions found", http_status=422)

    yes_available = pos_row.yes_volume - pos_row.yes_pending_sell
    no_available = pos_row.no_volume - pos_row.no_pending_sell
    max_burnable = min(yes_available, no_available)

    if quantity > max_burnable:
        raise AppError(
            5001,
            f"Insufficient available shares: can burn max {max_burnable}, requested {quantity}",
            http_status=422,
        )

    # Step 4: Calculate cost releases (weighted average)
    yes_cost_release = (
        (pos_row.yes_cost_sum * quantity) // pos_row.yes_volume
        if pos_row.yes_volume > 0
        else 0
    )
    no_cost_release = (
        (pos_row.no_cost_sum * quantity) // pos_row.no_volume
        if pos_row.no_volume > 0
        else 0
    )

    # Step 5: Deduct positions
    await db.execute(
        text(
            "UPDATE positions SET "
            "yes_volume = yes_volume - :qty, "
            "yes_cost_sum = yes_cost_sum - :yes_cost, "
            "no_volume = no_volume - :qty, "
            "no_cost_sum = no_cost_sum - :no_cost "
            "WHERE user_id = :uid AND market_id = :mid"
        ),
        {
            "qty": quantity,
            "yes_cost": yes_cost_release,
            "no_cost": no_cost_release,
            "uid": user_id,
            "mid": market_id,
        },
    )

    # Step 6: Reduce market reserve and credit AMM account
    recovery_cents = quantity * RECOVERY_PER_SHARE_CENTS
    await db.execute(
        text(
            "UPDATE markets SET reserve_balance = reserve_balance - :amount WHERE id = :mid"
        ),
        {"amount": recovery_cents, "mid": market_id},
    )
    await db.execute(
        text(
            "UPDATE accounts SET available_balance = available_balance + :amount, "
            "version = version + 1 WHERE user_id = :uid"
        ),
        {"amount": recovery_cents, "uid": user_id},
    )

    # Step 7: Write ledger entries
    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(id, user_id, entry_type, amount_cents, reference_type, reference_id, created_at) "
            "VALUES (:id, :uid, 'BURN_REVENUE', :amount, 'AMM_BURN', :ref, NOW())"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "amount": recovery_cents,
            "ref": idempotency_key,
        },
    )
    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(id, user_id, entry_type, amount_cents, reference_type, reference_id, created_at) "
            "VALUES (:id, :uid, 'BURN_RESERVE_OUT', :amount, 'AMM_BURN', :ref, NOW())"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": "SYSTEM",
            "amount": -recovery_cents,
            "ref": idempotency_key,
        },
    )

    # Step 8: Audit trade record
    await db.execute(
        text(
            "INSERT INTO trades "
            "(id, market_id, buy_order_id, sell_order_id, buy_user_id, sell_user_id, "
            "scenario, price_cents, quantity, maker_fee, taker_fee, created_at) "
            "VALUES (:id, :mid, :id, :id, 'SYSTEM', :seller, "
            "'BURN', 50, :qty, 0, 0, NOW())"
        ),
        {
            "id": str(uuid.uuid4()),
            "mid": market_id,
            "seller": user_id,
            "qty": quantity,
        },
    )

    # Step 9: Read updated state for response
    pos_final = await db.execute(
        text(
            "SELECT yes_volume, no_volume FROM positions "
            "WHERE user_id = :uid AND market_id = :mid"
        ),
        {"uid": user_id, "mid": market_id},
    )
    pos_f = pos_final.fetchone()

    bal_final = await db.execute(
        text("SELECT available_balance FROM accounts WHERE user_id = :uid"),
        {"uid": user_id},
    )
    bal_f = bal_final.fetchone()

    return {
        "market_id": market_id,
        "burned_quantity": quantity,
        "recovered_cents": recovery_cents,
        "new_yes_inventory": pos_f.yes_volume if pos_f else 0,
        "new_no_inventory": pos_f.no_volume if pos_f else 0,
        "remaining_balance_cents": bal_f.available_balance if bal_f else 0,
    }
