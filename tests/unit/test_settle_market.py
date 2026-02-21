"""Unit tests for pm_clearing settle_market (market settlement payout)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_clearing.domain.settlement import settle_market


class TestSettleMarketYesOutcome:
    @pytest.mark.asyncio
    async def test_yes_winner_credited_100_per_share(self) -> None:
        """YES outcome: user with yes_volume=10 gets credited 1000 cents."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = [("user1", 10, 0)]
        other_mock = MagicMock()
        # side_effect order: GET_POSITIONS, CREDIT user1, CLEAR user1, SETTLE_MARKET
        db.execute.side_effect = [positions_mock, other_mock, other_mock, other_mock]

        await settle_market("mkt-1", "YES", db)

        calls = db.execute.call_args_list
        assert len(calls) == 4

        # Second call must include amount=1000 (10 * 100)
        credit_kwargs = calls[1].args[1]
        assert credit_kwargs["user_id"] == "user1"
        assert credit_kwargs["amount"] == 1000

        # Third call: clear position
        clear_kwargs = calls[2].args[1]
        assert clear_kwargs["user_id"] == "user1"
        assert clear_kwargs["market_id"] == "mkt-1"

        # Fourth call: settle market
        settle_kwargs = calls[3].args[1]
        assert settle_kwargs["market_id"] == "mkt-1"
        assert settle_kwargs["result"] == "YES"

    @pytest.mark.asyncio
    async def test_yes_winner_with_large_volume(self) -> None:
        """YES outcome: payout scales linearly with yes_volume."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = [("user2", 500, 0)]
        other_mock = MagicMock()
        db.execute.side_effect = [positions_mock, other_mock, other_mock, other_mock]

        await settle_market("mkt-2", "YES", db)

        credit_kwargs = db.execute.call_args_list[1].args[1]
        assert credit_kwargs["amount"] == 50000  # 500 * 100

    @pytest.mark.asyncio
    async def test_yes_outcome_no_volume_user_not_credited(self) -> None:
        """YES outcome: user with only no_volume gets position cleared but not credited."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = [("user3", 0, 7)]
        other_mock = MagicMock()
        # GET_POSITIONS, CLEAR user3 (no credit), SETTLE_MARKET → 3 calls total
        db.execute.side_effect = [positions_mock, other_mock, other_mock]

        await settle_market("mkt-3", "YES", db)

        calls = db.execute.call_args_list
        # Only 3 calls: GET_POSITIONS + CLEAR + SETTLE (no CREDIT)
        assert len(calls) == 3

        # Second call must be CLEAR (not CREDIT)
        clear_kwargs = calls[1].args[1]
        assert clear_kwargs["user_id"] == "user3"
        assert clear_kwargs["market_id"] == "mkt-3"


class TestSettleMarketNoOutcome:
    @pytest.mark.asyncio
    async def test_no_winner_credited_100_per_share(self) -> None:
        """NO outcome: user with no_volume=5 gets credited 500 cents."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = [("user4", 0, 5)]
        other_mock = MagicMock()
        db.execute.side_effect = [positions_mock, other_mock, other_mock, other_mock]

        await settle_market("mkt-4", "NO", db)

        calls = db.execute.call_args_list
        assert len(calls) == 4

        credit_kwargs = calls[1].args[1]
        assert credit_kwargs["user_id"] == "user4"
        assert credit_kwargs["amount"] == 500  # 5 * 100

        settle_kwargs = calls[3].args[1]
        assert settle_kwargs["result"] == "NO"

    @pytest.mark.asyncio
    async def test_no_outcome_yes_volume_user_not_credited(self) -> None:
        """NO outcome: user with only yes_volume loses — position cleared, no credit."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = [("user5", 8, 0)]
        other_mock = MagicMock()
        # GET_POSITIONS, CLEAR user5, SETTLE_MARKET → 3 calls
        db.execute.side_effect = [positions_mock, other_mock, other_mock]

        await settle_market("mkt-5", "NO", db)

        calls = db.execute.call_args_list
        assert len(calls) == 3


class TestSettleMarketMultipleUsers:
    @pytest.mark.asyncio
    async def test_multiple_users_yes_outcome(self) -> None:
        """YES outcome with multiple users: each winner credited individually."""
        db = AsyncMock()
        positions_mock = MagicMock()
        # user1 wins YES, user2 has only NO shares (loses), user3 wins YES
        positions_mock.fetchall.return_value = [
            ("user1", 10, 0),
            ("user2", 0, 5),
            ("user3", 20, 3),
        ]
        other_mock = MagicMock()
        # Calls: GET_POSITIONS
        #        CREDIT user1, CLEAR user1
        #        CLEAR user2 (no credit)
        #        CREDIT user3, CLEAR user3
        #        SETTLE_MARKET → total 8 calls
        db.execute.side_effect = [other_mock] * 8
        db.execute.side_effect = [
            positions_mock,  # GET_POSITIONS
            other_mock,      # CREDIT user1
            other_mock,      # CLEAR user1
            other_mock,      # CLEAR user2
            other_mock,      # CREDIT user3
            other_mock,      # CLEAR user3
            other_mock,      # SETTLE_MARKET
        ]

        await settle_market("mkt-6", "YES", db)

        calls = db.execute.call_args_list
        assert len(calls) == 7

        # CREDIT user1: 10 * 100 = 1000
        assert calls[1].args[1]["user_id"] == "user1"
        assert calls[1].args[1]["amount"] == 1000

        # CLEAR user1
        assert calls[2].args[1]["user_id"] == "user1"

        # CLEAR user2 (no credit call before this)
        assert calls[3].args[1]["user_id"] == "user2"

        # CREDIT user3: 20 * 100 = 2000
        assert calls[4].args[1]["user_id"] == "user3"
        assert calls[4].args[1]["amount"] == 2000

        # CLEAR user3
        assert calls[5].args[1]["user_id"] == "user3"

        # SETTLE_MARKET
        assert calls[6].args[1]["market_id"] == "mkt-6"
        assert calls[6].args[1]["result"] == "YES"


class TestSettleMarketEmptyPositions:
    @pytest.mark.asyncio
    async def test_empty_positions_no_error(self) -> None:
        """Empty positions table: settle_market completes without error."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = []
        other_mock = MagicMock()
        # GET_POSITIONS + SETTLE_MARKET → 2 calls
        db.execute.side_effect = [positions_mock, other_mock]

        await settle_market("mkt-7", "YES", db)

        calls = db.execute.call_args_list
        assert len(calls) == 2

        settle_kwargs = calls[1].args[1]
        assert settle_kwargs["market_id"] == "mkt-7"
        assert settle_kwargs["result"] == "YES"

    @pytest.mark.asyncio
    async def test_empty_positions_no_outcome(self) -> None:
        """Empty positions: NO outcome also completes without error."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = []
        other_mock = MagicMock()
        db.execute.side_effect = [positions_mock, other_mock]

        await settle_market("mkt-8", "NO", db)

        calls = db.execute.call_args_list
        assert len(calls) == 2
        assert calls[1].args[1]["result"] == "NO"


class TestSettleMarketSettledAtTimestamp:
    @pytest.mark.asyncio
    async def test_settled_at_is_set(self) -> None:
        """settle_market always sets settled_at in the SETTLE_MARKET SQL call."""
        db = AsyncMock()
        positions_mock = MagicMock()
        positions_mock.fetchall.return_value = []
        other_mock = MagicMock()
        db.execute.side_effect = [positions_mock, other_mock]

        await settle_market("mkt-9", "YES", db)

        settle_kwargs = db.execute.call_args_list[1].args[1]
        assert "settled_at" in settle_kwargs
        assert settle_kwargs["settled_at"] is not None
