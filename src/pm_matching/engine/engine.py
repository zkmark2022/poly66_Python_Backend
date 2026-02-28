"""MatchingEngine — stateful orchestrator for per-market order placement."""
import asyncio
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.fee import calc_fee, get_fee_trade_value
from src.pm_clearing.domain.invariants import verify_invariants_after_trade
from src.pm_clearing.domain.netting import execute_netting_if_needed
from src.pm_clearing.domain.service import settle_trade
from src.pm_clearing.infrastructure.fee_collector import (
    collect_fee_from_frozen,
    collect_fee_from_proceeds,
)
from src.pm_clearing.infrastructure.ledger import write_ledger, write_wal_event
from src.pm_clearing.infrastructure.trades_writer import write_trade
from src.pm_common.datetime_utils import utc_now
from src.pm_common.errors import AppError
from src.pm_matching.domain.models import TradeResult
from src.pm_matching.engine.matching_algo import match_order
from src.pm_matching.engine.order_book import OrderBook
from src.pm_matching.engine.scenario import determine_scenario
from src.pm_order.domain.models import Order
from src.pm_order.domain.repository import OrderRepositoryProtocol
from src.pm_order.domain.transformer import transform_order
from src.pm_risk.rules.balance_check import _calc_max_fee, check_and_freeze
from src.pm_risk.rules.market_status import check_market_active
from src.pm_risk.rules.order_limit import check_order_limit
from src.pm_risk.rules.price_range import check_price_range

logger = logging.getLogger(__name__)

_GET_MARKET_SQL = text("""
    SELECT id, status, reserve_balance, pnl_pool,
           total_yes_shares, total_no_shares,
           taker_fee_bps
    FROM markets WHERE id = :market_id FOR UPDATE
""")

_UPDATE_MARKET_SQL = text("""
    UPDATE markets
    SET reserve_balance = :reserve_balance,
        pnl_pool = :pnl_pool,
        total_yes_shares = :total_yes_shares,
        total_no_shares  = :total_no_shares,
        updated_at = NOW()
    WHERE id = :id
""")


class MarketState:
    """In-memory view of market row; mutated during clearing, flushed at end."""

    def __init__(self, row: Any) -> None:
        self.id: str = row.id
        self.status: str = row.status
        self.reserve_balance: int = row.reserve_balance
        self.pnl_pool: int = row.pnl_pool
        self.total_yes_shares: int = row.total_yes_shares
        self.total_no_shares: int = row.total_no_shares
        self.taker_fee_bps: int = row.taker_fee_bps


class MatchingEngine:
    def __init__(self) -> None:
        self._orderbooks: dict[str, OrderBook] = {}
        self._market_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_or_create_lock(self, market_id: str) -> asyncio.Lock:
        return self._market_locks[market_id]

    def _get_or_create_orderbook(self, market_id: str) -> OrderBook:
        if market_id not in self._orderbooks:
            self._orderbooks[market_id] = OrderBook(market_id=market_id)
        return self._orderbooks[market_id]

    async def rebuild_orderbook(self, market_id: str, db: AsyncSession) -> None:
        """Lazy rebuild from DB on startup or after error recovery."""
        rows = (
            await db.execute(
                text(
                    "SELECT id, user_id, book_type, book_direction, book_price,"
                    " remaining_quantity, created_at"
                    " FROM orders WHERE market_id = :mid"
                    " AND status IN ('OPEN','PARTIALLY_FILLED')"
                    " ORDER BY created_at ASC"
                ),
                {"mid": market_id},
            )
        ).fetchall()
        ob = OrderBook(market_id=market_id)
        from src.pm_matching.domain.models import BookOrder

        for row in rows:
            row_any: Any = row
            bo = BookOrder(
                order_id=row_any.id,
                user_id=row_any.user_id,
                book_type=row_any.book_type,
                quantity=row_any.remaining_quantity,
                created_at=row_any.created_at,
            )
            ob.add_order(bo, price=row_any.book_price, side=row_any.book_direction)
        self._orderbooks[market_id] = ob

    async def place_order(
        self, order: Order, repo: OrderRepositoryProtocol, db: AsyncSession
    ) -> tuple[Order, list[TradeResult], int]:
        """Main entry point. Returns (order, trades, netting_qty)."""
        lock = self._get_or_create_lock(order.market_id)
        async with lock:
            try:
                async with db.begin_nested():
                    return await self._place_order_inner(order, repo, db)
            except Exception:
                # Evict orderbook — will lazy-rebuild on next request
                self._orderbooks.pop(order.market_id, None)
                raise

    async def _place_order_inner(
        self, order: Order, repo: OrderRepositoryProtocol, db: AsyncSession
    ) -> tuple[Order, list[TradeResult], int]:
        # Risk checks
        await check_market_active(order.market_id, db)
        check_price_range(order.original_price)
        check_order_limit(order.quantity)

        # Transform
        book_type, book_dir, book_price = transform_order(
            order.original_side, order.original_direction, order.original_price
        )
        order.book_type = book_type
        order.book_direction = book_dir
        order.book_price = book_price

        # Freeze
        await check_and_freeze(order, db)

        # Save order to DB
        await repo.save(order, db)

        # WAL: ORDER_ACCEPTED
        await write_wal_event("ORDER_ACCEPTED", order.id, order.market_id, order.user_id, {}, db)

        # Load market row FOR UPDATE
        market_row: Any = (
            await db.execute(_GET_MARKET_SQL, {"market_id": order.market_id})
        ).fetchone()
        market = MarketState(market_row)

        # Match
        ob = self._get_or_create_orderbook(order.market_id)
        trade_results = match_order(order, ob)

        # Clear each fill
        trades_db: list[TradeResult] = []
        netting_qty = 0
        for tr in trade_results:
            buy_pnl, sell_pnl = await settle_trade(tr, market, db, fee_bps=market.taker_fee_bps)
            _sync_frozen_amount(order, order.remaining_quantity)
            await repo.update_status(order, db)
            # Update maker order status in DB
            await _update_maker_status(tr, repo, db)

            # Fee collection
            taker_is_buyer = tr.taker_order_id == tr.buy_order_id
            taker_book_type = tr.buy_book_type if taker_is_buyer else tr.sell_book_type
            taker_user_id = tr.buy_user_id if taker_is_buyer else tr.sell_user_id
            fee_base = get_fee_trade_value(
                taker_book_type, tr.price, tr.quantity, tr.buy_original_price
            )
            actual_fee = calc_fee(fee_base, market.taker_fee_bps)
            max_fee = _calc_max_fee(fee_base)
            if taker_book_type in ("NATIVE_BUY", "SYNTHETIC_SELL"):
                await collect_fee_from_frozen(taker_user_id, actual_fee, max_fee, db)
            else:
                await collect_fee_from_proceeds(taker_user_id, actual_fee, db)

            # Persist trade
            scenario_val = determine_scenario(tr.buy_book_type, tr.sell_book_type)
            await write_trade(tr, scenario_val.value, 0, actual_fee, buy_pnl, sell_pnl, db)

            # Netting for buyer
            nq = await execute_netting_if_needed(tr.buy_user_id, order.market_id, market, db)
            netting_qty += nq
            await write_wal_event(
                "ORDER_MATCHED",
                order.id,
                order.market_id,
                order.user_id,
                {"trade_qty": tr.quantity},
                db,
            )
            trades_db.append(tr)

        # Finalize
        self_trade_skipped = 0  # tracked by match_order (not yet exposed; placeholder)
        await self._finalize_order(order, ob, db, repo, self_trade_skipped)

        # Invariants (only if trades happened)
        if trade_results:
            await verify_invariants_after_trade(market, db)

        # Flush market row
        await db.execute(
            _UPDATE_MARKET_SQL,
            {
                "id": market.id,
                "reserve_balance": market.reserve_balance,
                "pnl_pool": market.pnl_pool,
                "total_yes_shares": market.total_yes_shares,
                "total_no_shares": market.total_no_shares,
            },
        )

        return order, trades_db, netting_qty

    async def _finalize_order(
        self,
        order: Order,
        ob: OrderBook,
        db: AsyncSession,
        repo: OrderRepositoryProtocol,
        self_trade_skipped: int,
    ) -> None:
        if order.remaining_quantity > 0:
            if order.time_in_force == "GTC":
                from src.pm_matching.domain.models import BookOrder

                bo = BookOrder(
                    order_id=order.id,
                    user_id=order.user_id,
                    book_type=order.book_type,
                    quantity=order.remaining_quantity,
                    created_at=order.created_at or utc_now(),
                )
                ob.add_order(bo, price=order.book_price, side=order.book_direction)
                if order.filled_quantity > 0:
                    await write_wal_event(
                        "ORDER_PARTIALLY_FILLED", order.id, order.market_id, order.user_id, {}, db
                    )
            else:  # IOC
                if order.filled_quantity == 0 and self_trade_skipped > 0:
                    raise AppError(
                        4003, "Self-trade prevented all fills for IOC order", http_status=400
                    )
                await self._unfreeze_remainder(order, db)
                order.status = "CANCELLED"
                await repo.update_status(order, db)
                await write_wal_event(
                    "ORDER_EXPIRED", order.id, order.market_id, order.user_id, {}, db
                )

    async def _unfreeze_remainder(self, order: Order, db: AsyncSession) -> None:
        if order.frozen_asset_type == "FUNDS":
            await db.execute(
                text("""
                    UPDATE accounts SET available_balance=available_balance+:amount,
                    frozen_balance=frozen_balance-:amount, version=version+1, updated_at=NOW()
                    WHERE user_id=:user_id
                """),
                {"user_id": order.user_id, "amount": order.frozen_amount},
            )
            await write_ledger(
                user_id=order.user_id,
                entry_type="ORDER_UNFREEZE",
                amount=order.frozen_amount,
                balance_after=0,
                reference_type="ORDER",
                reference_id=order.id,
                db=db,
            )
        elif order.frozen_asset_type == "YES_SHARES":
            await db.execute(
                text(
                    "UPDATE positions SET yes_pending_sell=yes_pending_sell-:qty, updated_at=NOW()"
                    " WHERE user_id=:user_id AND market_id=:market_id"
                ),
                {
                    "user_id": order.user_id,
                    "market_id": order.market_id,
                    "qty": order.remaining_quantity,
                },
            )
        else:
            await db.execute(
                text(
                    "UPDATE positions SET no_pending_sell=no_pending_sell-:qty, updated_at=NOW()"
                    " WHERE user_id=:user_id AND market_id=:market_id"
                ),
                {
                    "user_id": order.user_id,
                    "market_id": order.market_id,
                    "qty": order.remaining_quantity,
                },
            )

    async def _cancel_order_by_row(self, row: Any, db: AsyncSession) -> None:
        """Cancel an order using a raw DB row (from SELECT FOR UPDATE).

        Removes from in-memory orderbook and unfreezes assets in DB.
        """
        market_id = str(row.market_id)
        order_id = str(row.id)

        # Remove from in-memory orderbook (safe if not present)
        ob = self._get_or_create_orderbook(market_id)
        ob.cancel_order(order_id)

        # Unfreeze assets
        if str(row.frozen_asset_type) == "FUNDS":
            await db.execute(
                text("""
                    UPDATE accounts SET available_balance=available_balance+:amt,
                    frozen_balance=frozen_balance-:amt, version=version+1, updated_at=NOW()
                    WHERE user_id=:uid
                """),
                {"uid": str(row.user_id), "amt": row.frozen_amount},
            )
            await write_ledger(
                user_id=str(row.user_id),
                entry_type="ORDER_UNFREEZE",
                amount=row.frozen_amount,
                balance_after=0,
                reference_type="ORDER",
                reference_id=order_id,
                db=db,
            )
        elif str(row.frozen_asset_type) == "YES_SHARES":
            await db.execute(
                text(
                    "UPDATE positions SET yes_pending_sell=yes_pending_sell-:qty,"
                    " updated_at=NOW() WHERE user_id=:uid AND market_id=:mid"
                ),
                {"uid": str(row.user_id), "mid": market_id, "qty": row.frozen_amount},
            )
        else:  # NO_SHARES
            await db.execute(
                text(
                    "UPDATE positions SET no_pending_sell=no_pending_sell-:qty,"
                    " updated_at=NOW() WHERE user_id=:uid AND market_id=:mid"
                ),
                {"uid": str(row.user_id), "mid": market_id, "qty": row.frozen_amount},
            )

        # Mark order CANCELLED in DB
        await db.execute(
            text("UPDATE orders SET status='CANCELLED', updated_at=NOW() WHERE id=:oid"),
            {"oid": order_id},
        )

    async def replace_order(
        self, old_order_id: str, new_order_params: Any, user_id: str, db: AsyncSession
    ) -> dict:
        """Atomic Replace: cancel old order + place new order in a single transaction.

        See interface contract v1.4 §3.1.

        Error codes:
        - 6002: old order not found
        - 6004: old order not owned by user_id
        - 6003: old order already fully filled
        - 6001: old order partially filled (cancel remainder, reject new)
        - 6005: new order market_id != old order market_id
        """
        # Step 1: Load old order (row-level lock)
        old_result = await db.execute(
            text(
                "SELECT id, user_id, status, filled_quantity, remaining_quantity,"
                " market_id, frozen_amount, frozen_asset_type, quantity"
                " FROM orders WHERE id = :oid FOR UPDATE"
            ),
            {"oid": old_order_id},
        )
        old_order_row = old_result.fetchone()

        if old_order_row is None:
            raise AppError(
                code=6002, message="Old order not found", http_status=404
            )

        if str(old_order_row.user_id) != str(user_id):
            raise AppError(
                code=6004, message="Old order not owned by requesting user", http_status=403
            )

        if old_order_row.status == "FILLED":
            raise AppError(
                code=6003, message="Old order already fully filled", http_status=422
            )

        if old_order_row.filled_quantity > 0:
            # Partially filled: cancel remainder, reject replacement
            await self._cancel_order_by_row(old_order_row, db)
            raise AppError(
                code=6001,
                message="Old order partially filled; remainder cancelled, replacement rejected",
                http_status=422,
            )

        # Step 2: Validate market_id consistency
        if str(old_order_row.market_id) != str(new_order_params.market_id):
            raise AppError(
                code=6005,
                message="New order market_id must match old order market_id",
                http_status=422,
            )

        market_id = str(old_order_row.market_id)

        # Step 3: Atomic replace within market lock
        async with self._market_locks[market_id]:
            # Cancel old order (remove from book + unfreeze + DB update)
            await self._cancel_order_by_row(old_order_row, db)

            # Build new Order domain object
            from src.pm_order.domain.models import Order
            from src.pm_order.infrastructure.persistence import OrderRepository
            from src.pm_common.id_generator import generate_id
            from src.pm_common.datetime_utils import utc_now

            repo = OrderRepository()
            new_order = Order(
                id=generate_id(),
                client_order_id=new_order_params.client_order_id,
                market_id=new_order_params.market_id,
                user_id=user_id,
                original_side=new_order_params.side,
                original_direction=new_order_params.direction,
                original_price=new_order_params.price_cents,
                book_type="",
                book_direction="",
                book_price=0,
                quantity=new_order_params.quantity,
                time_in_force=new_order_params.time_in_force,
                status="OPEN",
                created_at=utc_now(),
                updated_at=utc_now(),
            )

            placed_order, trades, _ = await self._place_order_inner(new_order, repo, db)

        return {
            "old_order_id": old_order_id,
            "old_order_status": "CANCELLED",
            "old_order_filled_quantity": 0,
            "old_order_original_quantity": old_order_row.quantity,
            "new_order": {
                "id": placed_order.id,
                "status": placed_order.status,
                "filled_quantity": placed_order.filled_quantity,
                "remaining_quantity": placed_order.remaining_quantity,
            },
            "trades": [
                {
                    "buy_order_id": t.buy_order_id,
                    "sell_order_id": t.sell_order_id,
                    "price": t.price,
                    "quantity": t.quantity,
                }
                for t in trades
            ],
        }

    async def batch_cancel(
        self, market_id: str, user_id: str, cancel_scope: str, db: AsyncSession
    ) -> dict:
        """Batch cancel all AMM orders in a market.

        See interface contract v1.4 §3.2.
        cancel_scope is applied to original_direction:
        - ALL: cancel all OPEN/PARTIALLY_FILLED orders
        - BUY_ONLY: cancel only BUY original_direction orders
        - SELL_ONLY: cancel only SELL original_direction orders
        """
        # Build direction filter (safe: only hardcoded strings, validated by Pydantic)
        direction_clause = ""
        if cancel_scope == "BUY_ONLY":
            direction_clause = "AND original_direction = 'BUY'"
        elif cancel_scope == "SELL_ONLY":
            direction_clause = "AND original_direction = 'SELL'"

        params: dict[str, Any] = {"uid": user_id, "mid": market_id}

        result = await db.execute(
            text(
                "SELECT id, frozen_amount, frozen_asset_type, original_direction,"
                " user_id, market_id"
                " FROM orders"
                " WHERE user_id = :uid AND market_id = :mid"
                " AND status IN ('OPEN', 'PARTIALLY_FILLED')"
                f" {direction_clause}"
                " FOR UPDATE"
            ),
            params,
        )
        orders = result.fetchall()

        if not orders:
            return {
                "market_id": market_id,
                "cancelled_count": 0,
                "total_unfrozen_funds_cents": 0,
                "total_unfrozen_yes_shares": 0,
                "total_unfrozen_no_shares": 0,
            }

        total_funds = 0
        total_yes = 0
        total_no = 0

        # Update in-memory orderbook under market lock
        async with self._market_locks[market_id]:
            ob = self._get_or_create_orderbook(market_id)
            for order in orders:
                ob.cancel_order(str(order.id))

        # Accumulate unfrozen amounts
        for order in orders:
            asset_type = str(order.frozen_asset_type)
            if asset_type == "FUNDS":
                total_funds += order.frozen_amount
            elif asset_type == "YES_SHARES":
                total_yes += order.frozen_amount
            else:  # NO_SHARES
                total_no += order.frozen_amount

        # Bulk update order statuses
        order_ids = [str(o.id) for o in orders]
        await db.execute(
            text(
                "UPDATE orders SET status = 'CANCELLED', updated_at = NOW()"
                " WHERE id = ANY(:ids)"
            ),
            {"ids": order_ids},
        )

        # Bulk unfreeze funds
        if total_funds > 0:
            await db.execute(
                text(
                    "UPDATE accounts SET"
                    " available_balance = available_balance + :amt,"
                    " frozen_balance = frozen_balance - :amt,"
                    " version = version + 1"
                    " WHERE user_id = :uid"
                ),
                {"amt": total_funds, "uid": user_id},
            )

        # Bulk unfreeze YES shares
        if total_yes > 0:
            await db.execute(
                text(
                    "UPDATE positions SET yes_pending_sell = yes_pending_sell - :amt"
                    " WHERE user_id = :uid AND market_id = :mid"
                ),
                {"amt": total_yes, "uid": user_id, "mid": market_id},
            )

        # Bulk unfreeze NO shares
        if total_no > 0:
            await db.execute(
                text(
                    "UPDATE positions SET no_pending_sell = no_pending_sell - :amt"
                    " WHERE user_id = :uid AND market_id = :mid"
                ),
                {"amt": total_no, "uid": user_id, "mid": market_id},
            )

        return {
            "market_id": market_id,
            "cancelled_count": len(orders),
            "total_unfrozen_funds_cents": total_funds,
            "total_unfrozen_yes_shares": total_yes,
            "total_unfrozen_no_shares": total_no,
        }

    async def cancel_order(
        self, order_id: str, user_id: str, repo: OrderRepositoryProtocol, db: AsyncSession
    ) -> Order:
        order = await repo.get_by_id(order_id, db)
        if order is None:
            raise AppError(4004, "Order not found", http_status=404)
        if order.user_id != user_id:
            raise AppError(403, "Forbidden", http_status=403)
        if not order.is_cancellable:
            raise AppError(4006, "Order cannot be cancelled", http_status=422)

        lock = self._get_or_create_lock(order.market_id)
        async with lock:
            try:
                async with db.begin_nested():
                    ob = self._get_or_create_orderbook(order.market_id)
                    ob.cancel_order(order_id)
                    await self._unfreeze_remainder(order, db)
                    order.status = "CANCELLED"
                    await repo.update_status(order, db)
                    await write_wal_event(
                        "ORDER_CANCELLED", order.id, order.market_id, order.user_id, {}, db
                    )
                    return order
            except AppError:
                raise
            except Exception:
                self._orderbooks.pop(order.market_id, None)
                raise

    async def replace_order(
        self,
        old_order_id: str,
        new_order_params: Any,
        user_id: str,
        repo: OrderRepositoryProtocol,
        db: AsyncSession,
    ) -> dict:
        """Atomic Replace: cancel old order + place new order in a single transaction.

        See interface contract v1.4 §3.1.

        Error codes:
        - 6002: old order not found
        - 6004: old order not owned by user_id
        - 6003: old order already fully filled
        - 6001: old order partially filled (replacement rejected)
        - 6005: new order market_id != old order market_id
        """
        from src.pm_common.datetime_utils import utc_now
        from src.pm_common.id_generator import generate_id

        # Step 1: Load and validate old order (outside lock)
        old_order = await repo.get_by_id(old_order_id, db)
        if old_order is None:
            raise AppError(6002, "Old order not found", http_status=404)
        if str(old_order.user_id) != str(user_id):
            raise AppError(6004, "Old order not owned by requesting user", http_status=403)
        if old_order.status == "FILLED":
            raise AppError(6003, "Old order already fully filled", http_status=422)
        if old_order.filled_quantity > 0:
            raise AppError(
                6001,
                "Old order partially filled; replacement rejected. Cancel the old order first.",
                http_status=422,
            )
        if str(old_order.market_id) != str(new_order_params.market_id):
            raise AppError(
                6005,
                "New order market_id must match old order market_id",
                http_status=422,
            )

        market_id = str(old_order.market_id)

        # Step 2: Atomic cancel + place under market lock
        lock = self._get_or_create_lock(market_id)
        async with lock:
            try:
                async with db.begin_nested():
                    # Cancel old order inline (no re-lock)
                    ob = self._get_or_create_orderbook(market_id)
                    ob.cancel_order(old_order_id)
                    await self._unfreeze_remainder(old_order, db)
                    old_order.status = "CANCELLED"
                    await repo.update_status(old_order, db)
                    await write_wal_event(
                        "ORDER_CANCELLED",
                        old_order.id,
                        market_id,
                        user_id,
                        {"replace_reason": "atomic_replace"},
                        db,
                    )

                    # Place new order inline (no re-lock via _place_order_inner)
                    new_order = Order(
                        id=generate_id(),
                        client_order_id=new_order_params.client_order_id,
                        market_id=new_order_params.market_id,
                        user_id=user_id,
                        original_side=new_order_params.side,
                        original_direction=new_order_params.direction,
                        original_price=new_order_params.price_cents,
                        book_type="",
                        book_direction="",
                        book_price=0,
                        quantity=new_order_params.quantity,
                        time_in_force=new_order_params.time_in_force,
                        status="OPEN",
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    new_order, trades, netting_qty = await self._place_order_inner(
                        new_order, repo, db
                    )

            except AppError:
                raise
            except Exception:
                self._orderbooks.pop(market_id, None)
                raise

        return {
            "old_order_id": old_order_id,
            "old_order_status": "CANCELLED",
            "old_order_filled_quantity": old_order.filled_quantity,
            "old_order_original_quantity": old_order.quantity,
            "new_order": {
                "id": new_order.id,
                "client_order_id": new_order.client_order_id,
                "status": new_order.status,
                "quantity": new_order.quantity,
                "filled_quantity": new_order.filled_quantity,
                "remaining_quantity": new_order.remaining_quantity,
            },
            "trades": [
                {
                    "buy_order_id": t.buy_order_id,
                    "sell_order_id": t.sell_order_id,
                    "price": t.price,
                    "quantity": t.quantity,
                }
                for t in trades
            ],
        }

    async def batch_cancel(
        self,
        market_id: str,
        user_id: str,
        cancel_scope: str,
        db: AsyncSession,
    ) -> dict:
        """Batch cancel all AMM orders in a market.

        See interface contract v1.4 §3.2.
        cancel_scope: ALL | BUY_ONLY | SELL_ONLY (based on original_direction).
        """
        from sqlalchemy import text as sql_text

        direction_filter = ""
        if cancel_scope == "BUY_ONLY":
            direction_filter = "AND original_direction = 'BUY'"
        elif cancel_scope == "SELL_ONLY":
            direction_filter = "AND original_direction = 'SELL'"

        result = await db.execute(
            sql_text(
                f"SELECT id, frozen_amount, frozen_asset_type, original_direction "  # noqa: S608
                f"FROM orders "
                f"WHERE user_id = :uid AND market_id = :mid "
                f"AND status IN ('OPEN', 'PARTIALLY_FILLED') "
                f"{direction_filter} "
                f"FOR UPDATE"
            ),
            {"uid": user_id, "mid": market_id},
        )
        orders = result.fetchall()

        if not orders:
            return {
                "market_id": market_id,
                "cancelled_count": 0,
                "total_unfrozen_funds_cents": 0,
                "total_unfrozen_yes_shares": 0,
                "total_unfrozen_no_shares": 0,
            }

        total_funds = 0
        total_yes = 0
        total_no = 0

        lock = self._get_or_create_lock(market_id)
        async with lock:
            ob = self._orderbooks.get(market_id)
            for order in orders:
                if ob:
                    ob.cancel_order(order.id)
                if order.frozen_asset_type == "FUNDS":
                    total_funds += order.frozen_amount
                elif order.frozen_asset_type == "YES_SHARES":
                    total_yes += order.frozen_amount
                elif order.frozen_asset_type == "NO_SHARES":
                    total_no += order.frozen_amount

            # Bulk cancel in DB
            order_ids = [o.id for o in orders]
            await db.execute(
                sql_text(
                    "UPDATE orders SET status = 'CANCELLED', updated_at = NOW() "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": order_ids},
            )

            # Bulk unfreeze
            if total_funds > 0:
                await db.execute(
                    sql_text(
                        "UPDATE accounts SET "
                        "available_balance = available_balance + :amt, "
                        "frozen_balance = frozen_balance - :amt, "
                        "version = version + 1 "
                        "WHERE user_id = :uid"
                    ),
                    {"amt": total_funds, "uid": user_id},
                )
            if total_yes > 0:
                await db.execute(
                    sql_text(
                        "UPDATE positions SET yes_pending_sell = yes_pending_sell - :amt "
                        "WHERE user_id = :uid AND market_id = :mid"
                    ),
                    {"amt": total_yes, "uid": user_id, "mid": market_id},
                )
            if total_no > 0:
                await db.execute(
                    sql_text(
                        "UPDATE positions SET no_pending_sell = no_pending_sell - :amt "
                        "WHERE user_id = :uid AND market_id = :mid"
                    ),
                    {"amt": total_no, "uid": user_id, "mid": market_id},
                )

        return {
            "market_id": market_id,
            "cancelled_count": len(orders),
            "total_unfrozen_funds_cents": total_funds,
            "total_unfrozen_yes_shares": total_yes,
            "total_unfrozen_no_shares": total_no,
        }


async def _update_maker_status(
    tr: TradeResult, repo: OrderRepositoryProtocol, db: AsyncSession
) -> None:
    """Load the resting (maker) order from DB and persist its updated fill state."""
    maker = await repo.get_by_id(tr.maker_order_id, db)
    if maker is None:
        return
    maker.filled_quantity += tr.quantity
    maker.remaining_quantity -= tr.quantity
    if maker.remaining_quantity <= 0:
        maker.remaining_quantity = 0
        maker.status = "FILLED"
    else:
        maker.status = "PARTIALLY_FILLED"
    _sync_frozen_amount(maker, maker.remaining_quantity)
    await repo.update_status(maker, db)


def _sync_frozen_amount(order: Order, remaining_qty: int) -> None:
    """Overwrite frozen_amount after each fill (avoids cumulative rounding errors)."""
    if order.frozen_asset_type == "FUNDS":
        if order.book_type == "NATIVE_BUY":
            remaining_value = order.book_price * remaining_qty
        else:  # SYNTHETIC_SELL
            remaining_value = order.original_price * remaining_qty
        order.frozen_amount = remaining_value + _calc_max_fee(remaining_value)
    else:
        order.frozen_amount = remaining_qty
