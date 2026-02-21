import pytest

from src.pm_common.enums import TradeScenario
from src.pm_matching.engine.scenario import determine_scenario


@pytest.mark.parametrize("buy_type,sell_type,expected", [
    ("NATIVE_BUY",    "SYNTHETIC_SELL", TradeScenario.MINT),
    ("NATIVE_BUY",    "NATIVE_SELL",    TradeScenario.TRANSFER_YES),
    ("SYNTHETIC_BUY", "SYNTHETIC_SELL", TradeScenario.TRANSFER_NO),
    ("SYNTHETIC_BUY", "NATIVE_SELL",    TradeScenario.BURN),
])
def test_determine_scenario(buy_type: str, sell_type: str, expected: TradeScenario) -> None:
    assert determine_scenario(buy_type, sell_type) == expected
