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
