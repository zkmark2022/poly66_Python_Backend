"""Global enums — must match DB CHECK constraints exactly.

Ref: Planning/Detail_Design/01_全局约定与数据库设计.md §4.1
"""

from enum import Enum


class MarketStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    HALTED = "HALTED"
    RESOLVED = "RESOLVED"
    SETTLED = "SETTLED"
    VOIDED = "VOIDED"


class BookType(str, Enum):
    """订单簿身份: 标识订单在单一 YES 订单簿中的来源和角色"""
    NATIVE_BUY = "NATIVE_BUY"
    NATIVE_SELL = "NATIVE_SELL"
    SYNTHETIC_BUY = "SYNTHETIC_BUY"
    SYNTHETIC_SELL = "SYNTHETIC_SELL"


class TradeScenario(str, Enum):
    """撮合场景: 由 buy/sell 的 BookType 组合决定"""
    MINT = "MINT"
    TRANSFER_YES = "TRANSFER_YES"
    TRANSFER_NO = "TRANSFER_NO"
    BURN = "BURN"


class FrozenAssetType(str, Enum):
    """冻结资产类型: 撤单时据此解冻到对应账户"""
    FUNDS = "FUNDS"
    YES_SHARES = "YES_SHARES"
    NO_SHARES = "NO_SHARES"


class OriginalSide(str, Enum):
    YES = "YES"
    NO = "NO"


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PriceType(str, Enum):
    LIMIT = "LIMIT"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"


class OrderStatus(str, Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class LedgerEntryType(str, Enum):
    # Deposit/Withdraw
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    # Order freeze/unfreeze (user side)
    ORDER_FREEZE = "ORDER_FREEZE"
    ORDER_UNFREEZE = "ORDER_UNFREEZE"
    # Mint (user + system paired)
    MINT_COST = "MINT_COST"
    MINT_RESERVE_IN = "MINT_RESERVE_IN"
    # Burn (user + system paired)
    BURN_REVENUE = "BURN_REVENUE"
    BURN_RESERVE_OUT = "BURN_RESERVE_OUT"
    # Transfer (user side)
    TRANSFER_PAYMENT = "TRANSFER_PAYMENT"
    TRANSFER_RECEIPT = "TRANSFER_RECEIPT"
    # Netting (user + system paired)
    NETTING = "NETTING"
    NETTING_RESERVE_OUT = "NETTING_RESERVE_OUT"
    # Fee (user + system paired)
    FEE = "FEE"
    FEE_REVENUE = "FEE_REVENUE"
    # Settlement (Phase 2)
    SETTLEMENT_PAYOUT = "SETTLEMENT_PAYOUT"
    SETTLEMENT_VOID = "SETTLEMENT_VOID"


class ResolutionResult(str, Enum):
    YES = "YES"
    NO = "NO"
    VOID = "VOID"
