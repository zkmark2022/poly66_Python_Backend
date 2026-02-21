def is_self_trade(incoming_user_id: str, resting_user_id: str) -> bool:
    """Predicate used by matching_algo to skip self-trade fills."""
    return incoming_user_id == resting_user_id
