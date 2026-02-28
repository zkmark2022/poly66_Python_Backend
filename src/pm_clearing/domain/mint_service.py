"""Privileged Mint — AMM special operation to create YES+NO share pairs.

Aligned with interface contract v1.4 §3.3:
- Deducts cost from AMM account (quantity × 100 cents)
- Increases market reserve_balance
- Increases market total_yes/no_shares
- Creates/updates AMM position
- Writes ledger entries (MINT_COST + MINT_RESERVE_IN)
- Idempotent via idempotency_key → ledger_entries.reference_id

Schema notes:
- ledger_entries.id is BIGSERIAL — do NOT specify id
- ledger_entries columns: amount (not amount_cents), balance_after (NOT NULL)
"""
import logging
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
            "SELECT amount, reference_id FROM ledger_entries "
            "WHERE reference_type = 'AMM_MINT' AND reference_id = :key "
            "LIMIT 1"
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
        raise AppError(code=3001, message="Market not found", http_status=404)
    if market_row.status != "ACTIVE":
        raise AppError(code=3002, message="Market is not active", http_status=422)

    # Step 3: Calculate cost
    cost_cents = quantity * COST_PER_SHARE_CENTS

    # Step 4: Read AMM account (FOR UPDATE for row locking)
    account_result = await db.execute(
        text(
            "SELECT available_balance, version FROM accounts "
            "WHERE user_id = :uid FOR UPDATE"
        ),
        {"uid": user_id},
    )
    account_row = account_result.fetchone()
    if account_row is None or account_row.available_balance < cost_cents:
        raise AppError(
            code=2001,
            message=f"Insufficient balance: need {cost_cents}, "
            f"have {account_row.available_balance if account_row else 0}",
            http_status=422,
        )

    old_balance = account_row.available_balance
    new_balance = old_balance - cost_cents

    # Step 5: Deduct from AMM account
    await db.execute(
        text(
            "UPDATE accounts SET available_balance = available_balance - :cost, "
            "version = version + 1 WHERE user_id = :uid"
        ),
        {"cost": cost_cents, "uid": user_id},
    )

    # Step 6: Increase market reserve_balance
    await db.execute(
        text(
            "UPDATE markets SET reserve_balance = reserve_balance + :cost "
            "WHERE id = :mid"
        ),
        {"cost": cost_cents, "mid": market_id},
    )

    # Step 7: Increase market shares
    await db.execute(
        text(
            "UPDATE markets SET "
            "total_yes_shares = total_yes_shares + :qty, "
            "total_no_shares = total_no_shares + :qty "
            "WHERE id = :mid"
        ),
        {"qty": quantity, "mid": market_id},
    )

    # Step 8: Upsert AMM positions (YES + NO)
    cost_half = quantity * INITIAL_FAIR_COST_PER_SHARE
    await db.execute(
        text(
            "INSERT INTO positions (user_id, market_id, yes_volume, yes_cost_sum, "
            "no_volume, no_cost_sum, yes_pending_sell, no_pending_sell) "
            "VALUES (:uid, :mid, :qty, :cost_half, :qty, :cost_half, 0, 0) "
            "ON CONFLICT (user_id, market_id) DO UPDATE SET "
            "yes_volume = positions.yes_volume + :qty, "
            "yes_cost_sum = positions.yes_cost_sum + :cost_half, "
            "no_volume = positions.no_volume + :qty, "
            "no_cost_sum = positions.no_cost_sum + :cost_half"
        ),
        {
            "uid": user_id,
            "mid": market_id,
            "qty": quantity,
            "cost_half": cost_half,
        },
    )

    # Step 9: Write ledger entries (no `id` — BIGSERIAL auto-generates)
    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(user_id, entry_type, amount, balance_after, reference_type, reference_id) "
            "VALUES (:uid, 'MINT_COST', :amount, :balance_after, 'AMM_MINT', :ref)"
        ),
        {
            "uid": user_id,
            "amount": -cost_cents,
            "balance_after": new_balance,
            "ref": idempotency_key,
        },
    )
    await db.execute(
        text(
            "INSERT INTO ledger_entries "
            "(user_id, entry_type, amount, balance_after, reference_type, reference_id) "
            "VALUES ('SYSTEM', 'MINT_RESERVE_IN', :amount, 0, 'AMM_MINT', :ref)"
        ),
        {
            "amount": cost_cents,
            "ref": idempotency_key,
        },
    )

    # Read updated positions and balance for response
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
        "remaining_balance_cents": bal_row.available_balance if bal_row else new_balance,
    }
