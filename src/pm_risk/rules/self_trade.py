# Canonical AMM bot user ID (UUID v4 with sentinel values).
# All comparisons normalise to str to guard against UUID-object inputs.
AMM_USER_ID: str = "00000000-0000-4000-a000-000000000001"


def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Return True iff the two orders belong to the same non-AMM user.

    The AMM bot is unconditionally exempt: it provides liquidity on both
    sides, so matching AMM orders against each other (or against regular
    users) must never be blocked by self-trade prevention.
    """
    uid_in = str(incoming_user_id)
    uid_rest = str(resting_user_id)
    if uid_in == AMM_USER_ID or uid_rest == AMM_USER_ID:
        return False
    return uid_in == uid_rest
