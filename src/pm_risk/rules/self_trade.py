"""Self-trade detection with AMM exemption.

AMM is exempt from self-trade detection because it legitimately
needs to have its YES buy orders match against its own NO sell orders
(which appear as SELL on the book). See data dictionary v1.3 §3.4.
"""
from src.pm_account.domain.constants import AMM_USER_ID

# Extensible set: add more market-maker user_ids if needed in the future
SELF_TRADE_EXEMPT_USERS: frozenset[str] = frozenset({AMM_USER_ID})


def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Check if incoming and resting orders would constitute a self-trade.

    Returns False (exempt) if incoming_user_id is in SELF_TRADE_EXEMPT_USERS.
    """
    if incoming_user_id in SELF_TRADE_EXEMPT_USERS:
        return False
    return incoming_user_id == resting_user_id
