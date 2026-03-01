AMM_USER_ID: str = "00000000-0000-4000-a000-000000000001"
_AMM_LOWER: str = AMM_USER_ID.lower()


def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Predicate used by matching_algo to skip self-trade fills.

    AMM user is exempt from self-trade prevention.
    UUID comparison is case-insensitive.
    """
    incoming = str(incoming_user_id).lower()
    resting = str(resting_user_id).lower()
    if incoming == _AMM_LOWER or resting == _AMM_LOWER:
        return False
    return incoming == resting
