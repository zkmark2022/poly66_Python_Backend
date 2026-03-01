"""Privileged Mint — AMM special operation to create YES+NO share pairs.

Aligned with interface contract v1.4 §3.3:
- Deducts cost from AMM account (quantity × 100 cents)
- Increases market reserve_balance and total_yes/no_shares
- Creates/updates AMM position (both YES and NO equally)
- Writes ledger entries (MINT_COST + MINT_RESERVE_IN)
- Writes audit trade record (scenario=MINT)
- Idempotent via idempotency_key → ledger_entries.reference_id
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.errors import AppError

logger = logging.getLogger(__name__)

COST_PER_SHARE_CENTS = 100
INITIAL_FAIR_COST_PER_SHARE = 50  # YES/NO each at 50 cents initial cost basis


async def execute_privileged_mint(
    user_id: str,
    market_id: str,
    quantity: int,
    idempotency_key: str,
    db: AsyncSession,
) -> dict:
    """Execute privileged mint within the caller's transaction.

    Returns dict with mint result data.
    Raises AppError on validation failure.
    """
    # Step 1: Idempotency check
    existing = await db.execute(
        text(
            "SELECT amount_cents, reference_id FROM ledger_entries "
            "WHERE reference_type = 'AMM_MINT' AND reference_id = :key"
        ),
        {"key": idempotency_key},
    )
    row = existing.fetchone()
    if row is not None:
        logger.info("Mint idempotency hit: key=%s", idempotency_key)
        return {"idempotent_hit": True, "idempotency_key": idempotency_key}

    # Step 2: Validate market status
    market_result = await db.execute(
        text("SELECT status FROM markets WHERE id = :mid"),
        {"mid": market_id},
    )
    market_row = market_result.fetchone()
    if market_row is None:
        raise AppError(3001, "Market not found", http_status=404)
    if market_row.status != "ACTIVE":
        raise AppError(3002, "Market is not active", http_status=422)

    # Step 3: Calculate cost
    cost_cents = quantity * COST_PER_SHARE_CENTS

    # Step 4: Deduct from AMM account (optimistic locking)
    account_result = await db.execute(
        text(
            "SELECT available_balance, version FROM accounts "
            "WHERE user_id = :uid FOR UPDATE"
        ),
        {"uid": user_id},
    )
    account_row = account_result.fetchone()
    if account_row is None or account_row.available_balance < cost_cents:
        available = account_row.available_balance if account_row else 0
        raise AppError(
            2001,
            f"Insufficient balance: need {cost_cents}, have {available}",
            http_status=422,
        )

    await db.execute(
        text(
            "UPDATE accounts SET available_balance = available_balance - :cost, "
            "version = version + 1 WHERE user_id = :uid"
        ),
        {"cost": cost_cents, "uid": user_id},
    )

    # Step 5: Increase market reserve and share counts
    await db.execute(
        text(
            "UPDATE markets SET "
            "reserve_balance = reserve_balance + :cost, "
            "total_yes_shares = total_yes_shares + :qty, "
            "total_no_shares = total_no_shares + :qty "
            "WHERE id = :mid"
        ),
        {"cost": cost_cents, "qty": quantity, "mid": market_id},
    )

    # Step 6: Update/insert positions (both YES and NO equally)
    cost_half = quantity * INITIAL_FAIR_COST_PER_SHARE
    await db.execute(
        text(
            "INSERT INTO positions "
            "(user_id, market_id, yes_volume, yes_cost_sum, no_volume, no_cost_sum, "
            "yes_pending_sell, no_pending_sell) "
            "VALUES (:uid, :mid, :qty, :cost_half, :qty, :cost_half, 0, 0) "
            "ON CONFLICT (user_id, market_id) DO UPDATE SET "
            "yes_volume = positions.yes_volume + :qty, "
            "yes_cost_sum = positions.yes_cost_sum + :cost_half, "
            "no_volume = positions.no_volume + :qty, "
            "no_cost_sum = positions.no_cost_sum + :cost_half"
        ),
        {"uid": user_id, "mid": market_id, "qty": quantity, "cost_half": cost_half},
    )

    # Step 7: Write ledger entries
    ledger_id_1 = str(uuid.uuid4())
    ledger_id_2 = str(uuid.uuid4())

    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(id, user_id, entry_type, amount_cents, reference_type, reference_id, created_at) "
            "VALUES (:id, :uid, 'MINT_COST', :amount, 'AMM_MINT', :ref, NOW())"
        ),
        {"id": ledger_id_1, "uid": user_id, "amount": -cost_cents, "ref": idempotency_key},
    )
    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(id, user_id, entry_type, amount_cents, reference_type, reference_id, created_at) "
            "VALUES (:id, :uid, 'MINT_RESERVE_IN', :amount, 'AMM_MINT', :ref, NOW())"
        ),
        {"id": ledger_id_2, "uid": "SYSTEM", "amount": cost_cents, "ref": idempotency_key},
    )

    # Step 8: Audit trade record
    trade_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO trades "
            "(id, market_id, buy_order_id, sell_order_id, buy_user_id, sell_user_id, "
            "scenario, price_cents, quantity, maker_fee, taker_fee, created_at) "
            "VALUES (:id, :mid, :id, :id, :buyer, 'SYSTEM', "
            "'MINT', 50, :qty, 0, 0, NOW())"
        ),
        {"id": trade_id, "mid": market_id, "buyer": user_id, "qty": quantity},
    )

    # Step 9: Read updated state for response
    pos_result = await db.execute(
        text(
            "SELECT yes_volume, no_volume FROM positions "
            "WHERE user_id = :uid AND market_id = :mid"
        ),
        {"uid": user_id, "mid": market_id},
    )
    pos_row = pos_result.fetchone()

    bal_result = await db.execute(
        text("SELECT available_balance FROM accounts WHERE user_id = :uid"),
        {"uid": user_id},
    )
    bal_row = bal_result.fetchone()

    return {
        "market_id": market_id,
        "minted_quantity": quantity,
        "cost_cents": cost_cents,
        "new_yes_inventory": pos_row.yes_volume if pos_row else quantity,
        "new_no_inventory": pos_row.no_volume if pos_row else quantity,
        "remaining_balance_cents": bal_row.available_balance if bal_row else 0,
    }
