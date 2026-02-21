"""Unified error codes and custom exceptions.

Error code ranges (per API doc §1.6):
  1xxx: Auth/User
  2xxx: Account
  3xxx: Market
  4xxx: Order
  5xxx: Position
  9xxx: System
"""


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = 500,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


# --- 1xxx: Auth/User ---

class UsernameExistsError(AppError):
    def __init__(self) -> None:
        super().__init__(1001, "Username already exists", 409)


class EmailExistsError(AppError):
    def __init__(self) -> None:
        super().__init__(1002, "Email already exists", 409)


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(1003, "Invalid username or password", 401)


class AccountDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__(1004, "Account is disabled", 403)


class InvalidRefreshTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(1005, "Refresh token is invalid or expired", 401)


# --- 2xxx: Account ---

class InsufficientBalanceError(AppError):
    def __init__(self, required: int, available: int) -> None:
        super().__init__(
            2001,
            f"Insufficient balance: required {required} cents, available {available} cents",
            422,
        )


class AccountNotFoundError(AppError):
    def __init__(self, user_id: str) -> None:
        super().__init__(2002, f"Account not found for user {user_id}", 404)


# --- 3xxx: Market ---

class MarketNotFoundError(AppError):
    def __init__(self, market_id: str) -> None:
        super().__init__(3001, f"Market not found: {market_id}", 404)


class MarketNotActiveError(AppError):
    def __init__(self, market_id: str) -> None:
        super().__init__(3002, f"Market is not active: {market_id}", 422)


# --- 4xxx: Order ---

class PriceOutOfRangeError(AppError):
    def __init__(self, price: int) -> None:
        super().__init__(4001, f"Price out of range: {price}", 422)


class OrderLimitExceededError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(4002, f"Order limit exceeded: {detail}", 422)


class SelfTradeError(AppError):
    def __init__(self) -> None:
        super().__init__(4003, "Self-trade prevented", 422)


class OrderNotFoundError(AppError):
    def __init__(self, order_id: str) -> None:
        super().__init__(4004, f"Order not found: {order_id}", 404)


class DuplicateOrderError(AppError):
    def __init__(self, client_order_id: str) -> None:
        super().__init__(4005, f"Duplicate client_order_id: {client_order_id}", 409)


class OrderNotCancellableError(AppError):
    def __init__(self, order_id: str, status: str) -> None:
        super().__init__(4006, f"Order {order_id} in status {status} cannot be cancelled", 422)


# --- 5xxx: Position ---

class InsufficientPositionError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(5001, f"Insufficient position: {detail}", 422)


# --- 9xxx: System ---

class RateLimitError(AppError):
    def __init__(self) -> None:
        super().__init__(9001, "Rate limit exceeded", 429)


class InternalError(AppError):
    def __init__(self, detail: str = "Internal server error") -> None:
        super().__init__(9002, detail, 500)
