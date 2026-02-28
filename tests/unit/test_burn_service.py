"""Test privileged burn business logic. See interface contract v1.4 §3.4."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pm_account.domain.constants import AMM_USER_ID


class TestPrivilegedBurn:
    @pytest.mark.asyncio
    async def test_burn_success_recovers_cash(self) -> None:
        """Burn 200 shares recovers 20000 cents (200 × 100)."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=1000,
            no_volume=1000,
            yes_pending_sell=0,
            no_pending_sell=0,
        )

        result = await execute_privileged_burn(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=200,
            idempotency_key="burn-001",
            db=db,
        )
        assert result["recovered_cents"] == 20000
        assert result["burned_quantity"] == 200

    @pytest.mark.asyncio
    async def test_burn_insufficient_yes_shares_raises(self) -> None:
        """Not enough YES shares should raise AppError code 5001."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=100,  # only 100, need 200
            no_volume=1000,
            yes_pending_sell=0,
            no_pending_sell=0,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_burn(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=200,
                idempotency_key="burn-002",
                db=db,
            )
        assert exc_info.value.code == 5001

    @pytest.mark.asyncio
    async def test_burn_respects_pending_sell(self) -> None:
        """Available = volume - pending_sell. Should fail if available < quantity."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=500,
            no_volume=500,
            yes_pending_sell=400,  # available = 100, need 200
            no_pending_sell=0,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_burn(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=200,
                idempotency_key="burn-003",
                db=db,
            )
        assert exc_info.value.code == 5001

    @pytest.mark.asyncio
    async def test_burn_idempotent(self) -> None:
        from src.pm_clearing.domain.burn_service import execute_privileged_burn

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(idempotent_exists=True)

        result = await execute_privileged_burn(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=200,
            idempotency_key="burn-001",
            db=db,
        )
        assert result.get("idempotent_hit") is True

    @staticmethod
    def _mock_burn_db_calls(**kwargs):
        calls = []
        if kwargs.get("idempotent_exists"):
            mock_result = MagicMock()
            mock_result.fetchone.return_value = MagicMock(
                amount=20000, reference_id="burn-001"
            )
            calls.append(mock_result)
        else:
            # Idempotency check: not found
            mock_idem = MagicMock()
            mock_idem.fetchone.return_value = None
            calls.append(mock_idem)

            # Market status check
            mock_market = MagicMock()
            mock_market.fetchone.return_value = MagicMock(
                status=kwargs.get("market_status", "ACTIVE")
            )
            calls.append(mock_market)

            # Position check
            mock_pos = MagicMock()
            mock_pos.fetchone.return_value = MagicMock(
                yes_volume=kwargs.get("yes_volume", 0),
                no_volume=kwargs.get("no_volume", 0),
                yes_pending_sell=kwargs.get("yes_pending_sell", 0),
                no_pending_sell=kwargs.get("no_pending_sell", 0),
                yes_cost_sum=kwargs.get("yes_volume", 0) * 50,
                no_cost_sum=kwargs.get("no_volume", 0) * 50,
            )
            calls.append(mock_pos)

            # Subsequent UPDATE/INSERT calls
            for _ in range(10):
                mock_op = MagicMock()
                mock_op.rowcount = 1
                calls.append(mock_op)

        return calls
