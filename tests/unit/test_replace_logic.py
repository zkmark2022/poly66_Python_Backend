"""Unit tests for replace_order logic — covers validation and eviction."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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
        "frozen_amount": 6513,  # 65*100=6500 + ceil(6500*20/10000)=13
        "frozen_asset_type": "FUNDS",
        "time_in_force": "GTC",
        "status": "OPEN",
    }
    defaults.update(kwargs)
    return Order(**defaults)


# ---------------------------------------------------------------------------
# Validation tests (before lock is acquired)
# ---------------------------------------------------------------------------


class TestReplaceOrderValidation:
    async def test_old_order_not_found_raises_6002(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 6002

    async def test_wrong_user_raises_6004(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="other-user", status="OPEN")
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 6004

    async def test_filled_order_raises_6003(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="FILLED")
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 6003

    async def test_partially_filled_order_raises_6001(self) -> None:
        engine = MatchingEngine()
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(
            user_id="user-1", status="PARTIALLY_FILLED", filled_quantity=50
        )
        db = AsyncMock()
        new_order = _make_order(id="order-2", client_order_id="client-2")

        with pytest.raises(AppError) as exc:
            await engine.replace_order("order-1", new_order, "user-1", repo, db)
        assert exc.value.code == 6001


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
        # begin_nested() must be a regular (non-async) call returning an async context manager
        db = AsyncMock()
        savepoint = AsyncMock()
        savepoint.__aenter__ = AsyncMock(side_effect=RuntimeError("DB failure"))
        savepoint.__aexit__ = AsyncMock(return_value=False)
        db.begin_nested = MagicMock(return_value=savepoint)

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
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        db = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="nonexistent",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                repo=repo,
                db=db,
            )
        assert exc_info.value.code == 6002

    @pytest.mark.asyncio
    async def test_replace_non_amm_order_returns_6004(self) -> None:
        """old_order belongs to different user → AppError code 6004."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(
            user_id="other-user", status="OPEN", filled_quantity=0, market_id="mkt-1"
        )
        db = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                repo=repo,
                db=db,
            )
        assert exc_info.value.code == 6004

    @pytest.mark.asyncio
    async def test_replace_filled_order_returns_6003(self) -> None:
        """old_order already fully filled → AppError code 6003."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(
            user_id=AMM_USER_ID, status="FILLED", filled_quantity=100, market_id="mkt-1"
        )
        db = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                repo=repo,
                db=db,
            )
        assert exc_info.value.code == 6003

    @pytest.mark.asyncio
    async def test_replace_partially_filled_returns_6001(self) -> None:
        """old_order partially filled → replacement rejected, code 6001."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(
            user_id=AMM_USER_ID,
            status="PARTIALLY_FILLED",
            filled_quantity=30,
            market_id="mkt-1",
        )
        db = AsyncMock()

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=self._make_new_params(),
                user_id=AMM_USER_ID,
                repo=repo,
                db=db,
            )
        assert exc_info.value.code == 6001

    @pytest.mark.asyncio
    async def test_replace_market_mismatch_returns_6005(self) -> None:
        """new_order market_id != old_order market_id → AppError code 6005."""
        from src.pm_account.domain.constants import AMM_USER_ID

        engine = self._make_engine()
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(
            user_id=AMM_USER_ID, status="OPEN", filled_quantity=0, market_id="mkt-1"
        )
        db = AsyncMock()
        new_params = self._make_new_params(market_id="mkt-2")

        with pytest.raises(AppError) as exc_info:
            await engine.replace_order(
                old_order_id="order-1",
                new_order_params=new_params,
                user_id=AMM_USER_ID,
                repo=repo,
                db=db,
            )
        assert exc_info.value.code == 6005

    @staticmethod
    def _make_engine() -> MatchingEngine:
        return MatchingEngine()

    @staticmethod
    def _make_new_params(market_id: str = "mkt-1") -> MagicMock:
        return MagicMock(
            client_order_id="amm_replace_001",
            market_id=market_id,
            side="YES",
            direction="SELL",
            price_cents=54,
            quantity=100,
            time_in_force="GTC",
        )
