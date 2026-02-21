"""Tests for pm_common.enums — all enum values must match DB CHECK constraints."""

from src.pm_common.enums import (
    BookType,
    FrozenAssetType,
    LedgerEntryType,
    MarketStatus,
    OrderDirection,
    OrderStatus,
    OriginalSide,
    PriceType,
    ResolutionResult,
    TimeInForce,
    TradeScenario,
)


class TestAllEnumsAreStr:
    """All enums inherit from (str, Enum) for JSON serialization."""

    def test_book_type_is_str(self) -> None:
        assert isinstance(BookType.NATIVE_BUY, str)
        assert BookType.NATIVE_BUY == "NATIVE_BUY"

    def test_trade_scenario_is_str(self) -> None:
        assert isinstance(TradeScenario.MINT, str)
        assert TradeScenario.MINT == "MINT"

    def test_order_status_is_str(self) -> None:
        assert isinstance(OrderStatus.NEW, str)
        assert OrderStatus.NEW == "NEW"


class TestBookType:
    def test_all_values(self) -> None:
        expected = {"NATIVE_BUY", "NATIVE_SELL", "SYNTHETIC_BUY", "SYNTHETIC_SELL"}
        assert {bt.value for bt in BookType} == expected


class TestTradeScenario:
    def test_all_values(self) -> None:
        expected = {"MINT", "TRANSFER_YES", "TRANSFER_NO", "BURN"}
        assert {ts.value for ts in TradeScenario} == expected


class TestFrozenAssetType:
    def test_all_values(self) -> None:
        expected = {"FUNDS", "YES_SHARES", "NO_SHARES"}
        assert {fa.value for fa in FrozenAssetType} == expected


class TestMarketStatus:
    def test_all_values(self) -> None:
        expected = {"DRAFT", "ACTIVE", "SUSPENDED", "HALTED", "RESOLVED", "SETTLED", "VOIDED"}
        assert {ms.value for ms in MarketStatus} == expected


class TestOrderStatus:
    def test_all_values(self) -> None:
        expected = {"NEW", "OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED"}
        assert {os.value for os in OrderStatus} == expected


class TestLedgerEntryType:
    def test_count(self) -> None:
        """16 entry types per design doc."""
        assert len(LedgerEntryType) == 16

    def test_user_side_types(self) -> None:
        user_types = {
            "DEPOSIT", "WITHDRAW", "ORDER_FREEZE", "ORDER_UNFREEZE",
            "MINT_COST", "BURN_REVENUE", "TRANSFER_PAYMENT", "TRANSFER_RECEIPT",
            "NETTING", "FEE", "SETTLEMENT_PAYOUT", "SETTLEMENT_VOID",
        }
        all_values = {le.value for le in LedgerEntryType}
        assert user_types.issubset(all_values)

    def test_system_side_types(self) -> None:
        system_types = {"MINT_RESERVE_IN", "BURN_RESERVE_OUT", "NETTING_RESERVE_OUT", "FEE_REVENUE"}
        all_values = {le.value for le in LedgerEntryType}
        assert system_types.issubset(all_values)


class TestSimpleEnums:
    def test_original_side(self) -> None:
        assert {s.value for s in OriginalSide} == {"YES", "NO"}

    def test_order_direction(self) -> None:
        assert {d.value for d in OrderDirection} == {"BUY", "SELL"}

    def test_price_type(self) -> None:
        assert {p.value for p in PriceType} == {"LIMIT"}

    def test_time_in_force(self) -> None:
        assert {t.value for t in TimeInForce} == {"GTC", "IOC"}

    def test_resolution_result(self) -> None:
        assert {r.value for r in ResolutionResult} == {"YES", "NO", "VOID"}
