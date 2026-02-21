"""Domain events for pm_account — TODO: implement in Phase 2.

Phase 2 events to add:
  - BalanceChanged(user_id, old_balance, new_balance, entry_id)
  - PositionChanged(user_id, market_id, side, old_volume, new_volume)

Use case: decouple async notifications (WebSocket, email) from core balance logic.
Implementation: Redis Pub/Sub or internal asyncio.Queue.
"""
