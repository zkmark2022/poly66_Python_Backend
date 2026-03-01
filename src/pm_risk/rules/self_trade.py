"""Self-trade detection with AMM exemption.

AMM is exempt from self-trade detection because it legitimately
needs to have its YES buy orders match against its own NO sell orders
(which appear as SELL on the book). See data dictionary v1.3 §3.4.
"""
from src.pm_account.domain.constants import AMM_USER_ID  # noqa: F401 (re-exported)

_AMM_LOWER: str = AMM_USER_ID.lower()

# Extensible set: add more market-maker user_ids if needed in the future
SELF_TRADE_EXEMPT_USERS: frozenset[str] = frozenset({AMM_USER_ID})


def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Predicate used by matching_algo to skip self-trade fills.

    Returns False (not a blocked self-trade) when either party is an exempt
    system account such as the AMM market maker.
    UUID comparison is case-insensitive.
    """
    uid_in = str(incoming_user_id).lower()
    uid_rest = str(resting_user_id).lower()
    if uid_in == _AMM_LOWER or uid_rest == _AMM_LOWER:
        return False
    return uid_in == uid_rest
