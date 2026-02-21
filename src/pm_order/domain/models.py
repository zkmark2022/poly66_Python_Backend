"""Order domain model — pure dataclass, no SQLAlchemy dependency."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Order:
    id: str
    client_order_id: str
    market_id: str
    user_id: str
    # User original intent
    original_side: str  # YES / NO
    original_direction: str  # BUY / SELL
    original_price: int  # 1-99
    # Orderbook view (after transform)
    book_type: str  # NATIVE_BUY / NATIVE_SELL / SYNTHETIC_BUY / SYNTHETIC_SELL
    book_direction: str  # BUY / SELL
    book_price: int  # 1-99
    # Quantity tracking
    quantity: int  # original order size
    # Freeze info
    frozen_amount: int = 0
    frozen_asset_type: str = ""  # FUNDS / YES_SHARES / NO_SHARES
    # Control
    time_in_force: str = "GTC"
    status: str = "OPEN"
    cancel_reason: str | None = None
    filled_quantity: int = 0
    remaining_quantity: int = field(init=False)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.remaining_quantity = self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        return self.status in ("OPEN", "PARTIALLY_FILLED")

    @property
    def is_cancellable(self) -> bool:
        return self.status in ("OPEN", "PARTIALLY_FILLED")
