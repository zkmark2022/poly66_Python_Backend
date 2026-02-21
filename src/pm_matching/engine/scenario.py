"""Trade scenario determination based on buy/sell BookType combination.

Ref: Planning/Detail_Design/03_撮合引擎设计.md
"""

from src.pm_common.enums import TradeScenario


def determine_scenario(buy_book_type: str, sell_book_type: str) -> TradeScenario:
    """Determine the trade scenario from the buy and sell BookType strings.

    Matrix:
        NATIVE_BUY  + SYNTHETIC_SELL -> MINT          (new YES+NO shares minted)
        NATIVE_BUY  + NATIVE_SELL    -> TRANSFER_YES  (YES shares change hands)
        SYNTHETIC_BUY + SYNTHETIC_SELL -> TRANSFER_NO (NO shares change hands)
        SYNTHETIC_BUY + NATIVE_SELL  -> BURN          (YES+NO shares burned)
    """
    buy_native = buy_book_type == "NATIVE_BUY"
    sell_native = sell_book_type == "NATIVE_SELL"
    if buy_native and not sell_native:
        return TradeScenario.MINT
    if buy_native and sell_native:
        return TradeScenario.TRANSFER_YES
    if not buy_native and not sell_native:
        return TradeScenario.TRANSFER_NO
    return TradeScenario.BURN
