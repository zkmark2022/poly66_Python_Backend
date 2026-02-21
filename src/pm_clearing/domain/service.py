"""Clearing dispatcher — maps TradeScenario to the correct handler."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.scenarios.burn import clear_burn
from src.pm_clearing.domain.scenarios.mint import clear_mint
from src.pm_clearing.domain.scenarios.transfer_no import clear_transfer_no
from src.pm_clearing.domain.scenarios.transfer_yes import clear_transfer_yes
from src.pm_common.enums import TradeScenario
from src.pm_matching.domain.models import TradeResult
from src.pm_matching.engine.scenario import determine_scenario


async def settle_trade(
    trade: TradeResult,
    market: object,
    db: AsyncSession,
    fee_bps: int,
) -> None:
    """Determine scenario and dispatch to the appropriate clearing function."""
    scenario = determine_scenario(trade.buy_book_type, trade.sell_book_type)
    if scenario == TradeScenario.MINT:
        await clear_mint(trade, market, db)
    elif scenario == TradeScenario.TRANSFER_YES:
        await clear_transfer_yes(trade, market, db)
    elif scenario == TradeScenario.TRANSFER_NO:
        await clear_transfer_no(trade, market, db)
    else:
        await clear_burn(trade, market, db)
    # Fee collection and refund handled by caller (MatchingEngine)
