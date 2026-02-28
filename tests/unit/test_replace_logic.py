# tests/unit/test_replace_logic.py
"""Test Atomic Replace logic. See interface contract v1.4 §3.1."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pm_account.domain.constants import AMM_USER_ID


class TestAtomicReplace:
    @pytest.mark.asyncio
    async def test_replace_nonexistent_order_returns_6002(self) -> None:
        """old_order_id not found → AppError code 6002."""
        from src.pm_common.errors import AppError

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
