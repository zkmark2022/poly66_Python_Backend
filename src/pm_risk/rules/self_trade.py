from src.pm_account.domain.constants import AMM_USER_ID

# Users exempt from self-trade prevention (AMM may fill against its own resting orders).
SELF_TRADE_EXEMPT_USERS: frozenset[str] = frozenset({AMM_USER_ID})


def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Predicate used by matching_algo to skip self-trade fills.

    Returns False (not a blocked self-trade) when either party is an exempt
    system account such as the AMM market maker.
    """
    if incoming_user_id in SELF_TRADE_EXEMPT_USERS or resting_user_id in SELF_TRADE_EXEMPT_USERS:
        return False
    return incoming_user_id == resting_user_id
