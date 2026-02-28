"""Unit tests for replace_order logic — covers double-unfreeze prevention."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.pm_common.errors import AppError
from src.pm_matching.engine.engine import MatchingEngine, _adjust_freeze_delta, _compute_freeze_requirement
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
        "frozen_amount": 6513,  # 65*100=6500 + ceil(6500*20/10000)=13
        "frozen_asset_type": "FUNDS",
        "time_in_force": "GTC",
        "status": "OPEN",
    }
    defaults.update(kwargs)
    return Order(**defaults)


def _db_ok() -> AsyncMock:
    """DB mock where execute().fetchone() returns a row (success)."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("row",)
    mock_db.execute.return_value = mock_result
    return mock_db


def _db_no_row() -> AsyncMock:
    """DB mock where execute().fetchone() returns None (insufficient balance)."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_db.execute.return_value = mock_result
    return mock_db


# ---------------------------------------------------------------------------
# Validation tests (before lock is acquired)
# ---------------------------------------------------------------------------


class TestReplaceOrderValidation:
    async def test_old_order_not_found_raises_4004(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 4004

    async def test_wrong_user_raises_403(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="other-user", status="OPEN")
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 403

    async def test_filled_order_raises_4006(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="FILLED")
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 4006

    async def test_cancelled_order_raises_4006(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="CANCELLED")
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 4006

    async def test_partially_filled_order_is_replaceable(self) -> None:
        """PARTIALLY_FILLED orders should be replaceable (is_cancellable is True)."""
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(
            user_id="user-1", status="PARTIALLY_FILLED", filled_quantity=50
        )
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        # Should not raise 4006 — inner logic raises because db isn't fully mocked
        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code != 4006


# ---------------------------------------------------------------------------
# _compute_freeze_requirement unit tests
# ---------------------------------------------------------------------------


class TestComputeFreezeRequirement:
    def test_native_buy_freezes_funds(self) -> None:
        order = _make_order(book_type="NATIVE_BUY", original_price=65, quantity=100)
        asset_type, amount = _compute_freeze_requirement(order)
        assert asset_type == "FUNDS"
        # 65*100=6500, fee=ceil(6500*20/10000)=13
        assert amount == 6513

    def test_synthetic_sell_freezes_funds_at_original_price(self) -> None:
        order = _make_order(
            book_type="SYNTHETIC_SELL",
            original_price=35,
            book_price=65,
            quantity=100,
        )
        asset_type, amount = _compute_freeze_requirement(order)
        assert asset_type == "FUNDS"
        # 35*100=3500, fee=ceil(3500*20/10000)=7
        assert amount == 3507

    def test_native_sell_freezes_yes_shares(self) -> None:
        order = _make_order(book_type="NATIVE_SELL", quantity=50)
        asset_type, amount = _compute_freeze_requirement(order)
        assert asset_type == "YES_SHARES"
        assert amount == 50

    def test_synthetic_buy_freezes_no_shares(self) -> None:
        order = _make_order(book_type="SYNTHETIC_BUY", quantity=80)
        asset_type, amount = _compute_freeze_requirement(order)
        assert asset_type == "NO_SHARES"
        assert amount == 80


# ---------------------------------------------------------------------------
# _adjust_freeze_delta — the core security fix
# ---------------------------------------------------------------------------


class TestAdjustFreezeDeltaFunds:
    """Verify that only the DELTA is frozen/unfrozen, not the full amount."""

    async def test_increase_freezes_only_delta(self) -> None:
        """Old=5000, new=7000 → must freeze delta(2000), NOT 7000."""
        db = _db_ok()

        await _adjust_freeze_delta(
            old_asset_type="FUNDS",
            old_amount=5000,
            new_asset_type="FUNDS",
            new_amount=7000,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 1
        params = db.execute.call_args[0][1]
        # Must be 2000 (delta), NOT 7000 (full new amount)
        assert params["amount"] == 2000

    async def test_decrease_unfreezes_only_delta(self) -> None:
        """Old=7000, new=5000 → must unfreeze delta(2000), NOT 7000."""
        db = AsyncMock()

        await _adjust_freeze_delta(
            old_asset_type="FUNDS",
            old_amount=7000,
            new_asset_type="FUNDS",
            new_amount=5000,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 1
        params = db.execute.call_args[0][1]
        # Must be 2000 (delta), NOT 7000 (full old amount)
        assert params["amount"] == 2000

    async def test_equal_amounts_no_sql_executed(self) -> None:
        """Old==new → no freeze/unfreeze SQL should run."""
        db = AsyncMock()

        await _adjust_freeze_delta(
            old_asset_type="FUNDS",
            old_amount=5000,
            new_asset_type="FUNDS",
            new_amount=5000,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        db.execute.assert_not_called()

    async def test_increase_raises_on_insufficient_balance(self) -> None:
        """Insufficient available balance raises AppError."""
        db = _db_no_row()

        from src.pm_common.errors import InsufficientBalanceError

        with pytest.raises(InsufficientBalanceError):
            await _adjust_freeze_delta(
                old_asset_type="FUNDS",
                old_amount=5000,
                new_asset_type="FUNDS",
                new_amount=7000,
                user_id="user-1",
                market_id="mkt-1",
                db=db,
            )


class TestAdjustFreezeDeltaShares:
    async def test_yes_shares_increase_freezes_delta(self) -> None:
        db = _db_ok()

        await _adjust_freeze_delta(
            old_asset_type="YES_SHARES",
            old_amount=50,
            new_asset_type="YES_SHARES",
            new_amount=80,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 1
        params = db.execute.call_args[0][1]
        assert params["qty"] == 30  # delta only

    async def test_yes_shares_decrease_unfreezes_delta(self) -> None:
        db = AsyncMock()

        await _adjust_freeze_delta(
            old_asset_type="YES_SHARES",
            old_amount=80,
            new_asset_type="YES_SHARES",
            new_amount=50,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 1
        params = db.execute.call_args[0][1]
        assert params["qty"] == 30  # delta only

    async def test_no_shares_increase_freezes_delta(self) -> None:
        db = _db_ok()

        await _adjust_freeze_delta(
            old_asset_type="NO_SHARES",
            old_amount=40,
            new_asset_type="NO_SHARES",
            new_amount=60,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 1
        params = db.execute.call_args[0][1]
        assert params["qty"] == 20  # delta only


class TestAdjustFreezeDeltaAssetTypeChange:
    """When asset type changes, freeze new FIRST then unfreeze old."""

    async def test_funds_to_yes_shares_freezes_new_first(self) -> None:
        """Freeze YES shares before unfreezing funds — no double-free window."""
        call_order: list[str] = []

        db = AsyncMock()
        mock_result_ok = MagicMock()
        mock_result_ok.fetchone.return_value = ("row",)

        async def execute_side_effect(sql: Any, params: Any) -> Any:
            sql_text = str(sql)
            if "yes_pending_sell" in sql_text and "RETURNING" in sql_text:
                call_order.append("freeze_yes")
                return mock_result_ok
            elif "available_balance" in sql_text and "frozen_balance" in sql_text:
                call_order.append("unfreeze_funds")
                return MagicMock()
            return MagicMock()

        db.execute.side_effect = execute_side_effect

        await _adjust_freeze_delta(
            old_asset_type="FUNDS",
            old_amount=6513,
            new_asset_type="YES_SHARES",
            new_amount=100,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        # Freeze new MUST happen before unfreeze old
        assert call_order == ["freeze_yes", "unfreeze_funds"]

    async def test_yes_shares_to_funds_freezes_funds_first(self) -> None:
        """Freeze funds before unfreezing YES shares."""
        call_order: list[str] = []

        db = AsyncMock()
        mock_result_ok = MagicMock()
        mock_result_ok.fetchone.return_value = ("row",)

        async def execute_side_effect(sql: Any, params: Any) -> Any:
            sql_text = str(sql)
            if "available_balance" in sql_text and "RETURNING" in sql_text:
                call_order.append("freeze_funds")
                return mock_result_ok
            elif "yes_pending_sell" in sql_text and "RETURNING" not in sql_text:
                call_order.append("unfreeze_yes")
                return MagicMock()
            return MagicMock()

        db.execute.side_effect = execute_side_effect

        await _adjust_freeze_delta(
            old_asset_type="YES_SHARES",
            old_amount=100,
            new_asset_type="FUNDS",
            new_amount=6513,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert call_order == ["freeze_funds", "unfreeze_yes"]

    async def test_asset_type_change_two_sql_calls(self) -> None:
        """Asset type change requires exactly 2 SQL calls (freeze + unfreeze)."""
        db = _db_ok()

        await _adjust_freeze_delta(
            old_asset_type="FUNDS",
            old_amount=5000,
            new_asset_type="YES_SHARES",
            new_amount=100,
            user_id="user-1",
            market_id="mkt-1",
            db=db,
        )

        assert db.execute.call_count == 2


# ---------------------------------------------------------------------------
# replace_order orderbook eviction on exception
# ---------------------------------------------------------------------------


class TestReplaceOrderEviction:
    async def test_exception_in_inner_evicts_orderbook(self) -> None:
        """On unexpected error, the orderbook is evicted so it can be rebuilt."""
        engine = MatchingEngine()
        engine._orderbooks["mkt-1"] = MagicMock()  # pre-populate

        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="OPEN")

        # Simulate savepoint failing with a RuntimeError
        db = AsyncMock()
        savepoint = AsyncMock()
        savepoint.__aenter__ = AsyncMock(side_effect=RuntimeError("DB failure"))
        savepoint.__aexit__ = AsyncMock(return_value=False)
        db.begin_nested.return_value = savepoint

        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(RuntimeError):
            await engine.replace_order("order-1", new_order, "user-1", repo, db)

        assert "mkt-1" not in engine._orderbooks


# ---------------------------------------------------------------------------
# AMM Atomic Replace API tests (interface contract v1.4 §3.1)
# ---------------------------------------------------------------------------


class TestAtomicReplace:
    @pytest.mark.asyncio
    async def test_replace_nonexistent_order_returns_6002(self) -> None:
        """old_order_id not found → AppError code 6002."""
        from src.pm_common.errors import AppError
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="nonexistent",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                db=db,
            )
        assert exc_info.value.code == 6002

    @pytest.mark.asyncio
    async def test_replace_non_amm_order_returns_6004(self) -> None:
        """old_order belongs to different user → AppError code 6004."""
        from src.pm_common.errors import AppError
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            user_id="other-user", status="OPEN", filled_quantity=0, market_id="mkt-1"
        )
        db.execute.return_value = mock_result

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                db=db,
            )
        assert exc_info.value.code == 6004

    @pytest.mark.asyncio
    async def test_replace_filled_order_returns_6003(self) -> None:
        """old_order already fully filled → AppError code 6003."""
        from src.pm_common.errors import AppError
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            user_id=AMM_USER_ID, status="FILLED", filled_quantity=100, market_id="mkt-1"
        )
        db.execute.return_value = mock_result

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                db=db,
            )
        assert exc_info.value.code == 6003

    @pytest.mark.asyncio
    async def test_replace_partially_filled_returns_6001(self) -> None:
        """old_order partially filled → cancel remainder, return code 6001."""
        from src.pm_common.errors import AppError
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            user_id=AMM_USER_ID,
            status="PARTIALLY_FILLED",
            filled_quantity=30,
            remaining_quantity=70,
            market_id="mkt-1",
            frozen_amount=4550,
            frozen_asset_type="FUNDS",
        )
        db.execute.return_value = mock_result

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                db=db,
            )
        assert exc_info.value.code == 6001

    @pytest.mark.asyncio
    async def test_replace_market_mismatch_returns_6005(self) -> None:
        """new_order market_id != old_order market_id → AppError code 6005."""
        from src.pm_common.errors import AppError
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            user_id=AMM_USER_ID, status="OPEN", filled_quantity=0, market_id="mkt-1"
        )
        db.execute.return_value = mock_result

        new_params = self._make_new_params(market_id="mkt-2")

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=new_params,
                user_id=AMM_USER_ID,
                db=db,
            )
        assert exc_info.value.code == 6005

    @staticmethod
    def _make_engine():
        """Create a minimal MatchingEngine for replace_order testing."""
        from src.pm_matching.engine.engine import MatchingEngine
        return MatchingEngine()

    @staticmethod
    def _make_new_params(market_id: str = "mkt-1"):
        return MagicMock(
            client_order_id="amm_replace_001",
            market_id=market_id,
            side="YES",
            direction="SELL",
            price_cents=54,
            quantity=100,
            time_in_force="GTC",
        )
