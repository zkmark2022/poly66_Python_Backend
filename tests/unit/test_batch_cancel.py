"""Unit tests for batch_cancel — covers market lock acquisition and ordering."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pm_common.errors import AppError
from src.pm_matching.engine.engine import MatchingEngine
from src.pm_order.domain.models import Order


def _make_order(**kwargs: Any) -> Order:
    defaults: dict[str, Any] = {
        "id": "order-1",
        "client_order_id": "client-1",
        "market_id": "mkt-1",
        "user_id": "user-1",
        "original_side": "YES",
        "original_direction": "BUY",
        "original_price": 65,
        "book_type": "NATIVE_BUY",
        "book_direction": "BUY",
        "book_price": 65,
        "quantity": 100,
        "frozen_amount": 6513,
        "frozen_asset_type": "FUNDS",
        "time_in_force": "GTC",
        "status": "OPEN",
    }
    defaults.update(kwargs)
    return Order(**defaults)


def _make_db() -> AsyncMock:
    """DB mock with working begin_nested savepoint."""
    db = AsyncMock()
    savepoint = AsyncMock()
    savepoint.__aenter__ = AsyncMock(return_value=None)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested.return_value = savepoint
    db.execute.return_value = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Validation tests (before any lock is acquired)
# ---------------------------------------------------------------------------


class TestBatchCancelValidation:
    async def test_empty_list_returns_empty(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        db = AsyncMock()

        result = await engine.batch_cancel([], "user-1", repo, db)

        assert result == []
        repo.get_by_id.assert_not_called()

    async def test_order_not_found_raises_4004(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        db = AsyncMock()

        with pytest.raises(AppError) as exc:
            await engine.batch_cancel(["missing-id"], "user-1", repo, db)
        assert exc.value.code == 4004

    async def test_wrong_user_raises_403(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="other-user")
        db = AsyncMock()

        with pytest.raises(AppError) as exc:
            await engine.batch_cancel(["order-1"], "user-1", repo, db)
        assert exc.value.code == 403

    async def test_filled_order_raises_4006(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="FILLED")
        db = AsyncMock()

        with pytest.raises(AppError) as exc:
            await engine.batch_cancel(["order-1"], "user-1", repo, db)
        assert exc.value.code == 4006

    async def test_cancelled_order_raises_4006(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="CANCELLED")
        db = AsyncMock()

        with pytest.raises(AppError) as exc:
            await engine.batch_cancel(["order-1"], "user-1", repo, db)
        assert exc.value.code == 4006

    async def test_second_order_wrong_user_stops_before_cancelling_first(self) -> None:
        """Validation must complete for ALL orders before any cancellation occurs."""
        engine = MatchingEngine()
        repo = AsyncMock()
        # First order valid, second order wrong user
        repo.get_by_id.side_effect = [
            _make_order(id="order-1", user_id="user-1", status="OPEN"),
            _make_order(id="order-2", user_id="other-user", status="OPEN"),
        ]
        db = AsyncMock()

        with pytest.raises(AppError) as exc:
            await engine.batch_cancel(["order-1", "order-2"], "user-1", repo, db)
        assert exc.value.code == 403


# ---------------------------------------------------------------------------
# Successful cancellation tests
# ---------------------------------------------------------------------------


class TestBatchCancelSuccess:
    async def test_single_order_cancelled(self) -> None:
        engine = MatchingEngine()
        order = _make_order(user_id="user-1", status="OPEN", frozen_asset_type="FUNDS")
        repo = AsyncMock()
        repo.get_by_id.return_value = order
        db = _make_db()

        result = await engine.batch_cancel(["order-1"], "user-1", repo, db)

        assert len(result) == 1
        assert result[0].status == "CANCELLED"
        repo.update_status.assert_called_once()

    async def test_multiple_orders_same_market_all_cancelled(self) -> None:
        engine = MatchingEngine()
        order1 = _make_order(id="o1", user_id="user-1", market_id="mkt-1", status="OPEN")
        order2 = _make_order(id="o2", user_id="user-1", market_id="mkt-1", status="OPEN")
        repo = AsyncMock()
        repo.get_by_id.side_effect = [order1, order2]
        db = _make_db()

        result = await engine.batch_cancel(["o1", "o2"], "user-1", repo, db)

        assert len(result) == 2
        assert all(o.status == "CANCELLED" for o in result)

    async def test_multiple_markets_each_gets_own_lock(self) -> None:
        """Orders from different markets must each acquire their market lock."""
        engine = MatchingEngine()
        order1 = _make_order(id="o1", user_id="user-1", market_id="mkt-1", status="OPEN")
        order2 = _make_order(id="o2", user_id="user-1", market_id="mkt-2", status="OPEN")
        repo = AsyncMock()
        repo.get_by_id.side_effect = [order1, order2]
        db = _make_db()

        result = await engine.batch_cancel(["o1", "o2"], "user-1", repo, db)

        assert len(result) == 2
        # Both market locks must have been created
        assert "mkt-1" in engine._market_locks
        assert "mkt-2" in engine._market_locks

    async def test_locks_acquired_in_sorted_market_order(self) -> None:
        """Markets must be locked in sorted order to prevent deadlock."""
        engine = MatchingEngine()
        # mkt-B and mkt-A: sorted order should be mkt-A then mkt-B
        order_b = _make_order(id="ob", user_id="user-1", market_id="mkt-B", status="OPEN")
        order_a = _make_order(id="oa", user_id="user-1", market_id="mkt-A", status="OPEN")
        repo = AsyncMock()
        repo.get_by_id.side_effect = [order_b, order_a]
        db = _make_db()

        lock_acquisition_order: list[str] = []
        original_get_lock = engine._get_or_create_lock

        def tracking_get_lock(market_id: str) -> Any:
            lock_acquisition_order.append(market_id)
            return original_get_lock(market_id)

        engine._get_or_create_lock = tracking_get_lock  # type: ignore[method-assign]

        await engine.batch_cancel(["ob", "oa"], "user-1", repo, db)

        # Must be in sorted order regardless of input order
        assert lock_acquisition_order == sorted(lock_acquisition_order)

    async def test_shares_order_cancelled_correctly(self) -> None:
        """YES_SHARES frozen orders are unfrozen via positions table."""
        engine = MatchingEngine()
        order = _make_order(
            user_id="user-1",
            status="OPEN",
            book_type="NATIVE_SELL",
            frozen_asset_type="YES_SHARES",
            frozen_amount=100,
        )
        repo = AsyncMock()
        repo.get_by_id.return_value = order
        db = _make_db()

        result = await engine.batch_cancel(["order-1"], "user-1", repo, db)

        assert len(result) == 1
        assert result[0].status == "CANCELLED"
        # Verify positions table was touched (yes_pending_sell update)
        execute_calls = db.execute.call_args_list
        sql_texts = [str(c[0][0]) for c in execute_calls]
        assert any("yes_pending_sell" in s for s in sql_texts)


# ---------------------------------------------------------------------------
# Exception handling — orderbook eviction
# ---------------------------------------------------------------------------


class TestBatchCancelEviction:
    async def test_exception_evicts_orderbook(self) -> None:
        """On unexpected error, orderbook is evicted for safe rebuild."""
        engine = MatchingEngine()
        engine._orderbooks["mkt-1"] = MagicMock()  # pre-populate

        order = _make_order(user_id="user-1", status="OPEN")
        repo = AsyncMock()
        repo.get_by_id.return_value = order

        db = AsyncMock()
        savepoint = AsyncMock()
        savepoint.__aenter__ = AsyncMock(side_effect=RuntimeError("DB failure"))
        savepoint.__aexit__ = AsyncMock(return_value=False)
        db.begin_nested.return_value = savepoint

        with pytest.raises(RuntimeError):
            await engine.batch_cancel(["order-1"], "user-1", repo, db)

        assert "mkt-1" not in engine._orderbooks

    async def test_app_error_propagated_without_eviction(self) -> None:
        """AppError (e.g. 4004) should propagate without evicting orderbook."""
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = None  # 4004 — caught before savepoint
        db = AsyncMock()

        with pytest.raises(AppError):
            await engine.batch_cancel(["order-1"], "user-1", repo, db)

        # No orderbook was ever created, so no eviction needed
        assert len(engine._orderbooks) == 0


# ---------------------------------------------------------------------------
# AMM Batch Cancel API tests (interface contract v1.4 §3.2)
# ---------------------------------------------------------------------------


class TestBatchCancel:
    @pytest.mark.asyncio
    async def test_cancel_all_returns_count(self) -> None:
        """Cancel ALL scope should cancel all AMM orders in market."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = MatchingEngine()
        db = AsyncMock()

        # Mock: 3 active AMM orders
        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=500, frozen_asset_type="YES_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o3", frozen_amount=300, frozen_asset_type="NO_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["cancelled_count"] == 3

    @pytest.mark.asyncio
    async def test_cancel_no_active_orders(self) -> None:
        """No active orders → cancelled_count = 0, not an error."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = []
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["cancelled_count"] == 0

    @pytest.mark.asyncio
    async def test_cancel_buy_only_filters_correctly(self) -> None:
        """BUY_ONLY scope: cancel only BUY original_direction orders."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=2000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="BUY_ONLY",
            db=db,
        )
        assert result["cancelled_count"] == 2

    @pytest.mark.asyncio
    async def test_cancel_all_unfrozen_amounts_summed(self) -> None:
        """All unfrozen amounts (funds, yes_shares, no_shares) are summed correctly."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=50, frozen_asset_type="YES_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o3", frozen_amount=30, frozen_asset_type="NO_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["total_unfrozen_funds_cents"] == 1000
        assert result["total_unfrozen_yes_shares"] == 50
        assert result["total_unfrozen_no_shares"] == 30
        assert result["market_id"] == "mkt-1"
