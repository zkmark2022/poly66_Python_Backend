# AMM 机器人本体 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the AMM bot as an independent sidecar service. The bot connects to the matching engine via REST API, runs the A-S pricing model with three-layer pricing, manages inventory via Redis cache, and enforces a three-line defense risk system.

**Architecture:** Three-layer module architecture (Connector / Strategy / Risk Middleware). Single asyncio process managing multiple markets concurrently. REST polling for inventory sync (MVP, no Kafka).

**Tech Stack:** Python 3.12, asyncio, httpx (async HTTP), redis.asyncio, PyYAML, pydantic, pytest-asyncio

**Prerequisites:** Phase A (`2026-02-28-amm-prerequisites-plan.md`) must be fully implemented — AMM system account exists, Mint/Burn/Replace APIs available, netting bypass and self-trade exemption active.

**Key facts before you start:**
- AMM user_id: `00000000-0000-4000-a000-000000000001` (from `src/pm_account/domain/constants.py`)
- All amounts in integer cents. Price range [1, 99]. Fee: `(value * bps + 9999) // 10000`
- AMM base URL: `http://localhost:8000/api/v1`
- AMM-specific endpoints: `/api/v1/amm/mint`, `/api/v1/amm/burn`, `/api/v1/amm/orders/replace`, `/api/v1/amm/orders/batch-cancel`
- Standard endpoints: `/api/v1/orders`, `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/account/balance`, `/api/v1/positions/{market_id}`, `/api/v1/markets/{id}`
- Redis key patterns: `amm:inventory:{market_id}`, `amm:orders:{market_id}`, `amm:config:{market_id}`, `amm:state:{market_id}`
- Config: 87+ parameters in YAML, hot-updatable via Redis. See config handbook v1.3.
- A-S model: `r = s - q·γ·σ²·τ(h)`, `δ = γ·σ²·τ(h) + (2/γ)·ln(1 + γ/κ)`
- Run tests: `uv run pytest <path> -v`
- All test functions must have `-> None` return type
- Design doc: `Planning/Implementation/2026-02-28-amm-bot-design.md`

---

## Task 1: Project Scaffolding + AMM Enums

**Files:**
- Create: `src/amm/__init__.py`
- Create: `src/amm/models/__init__.py`
- Create: `src/amm/models/enums.py`
- Test: `tests/unit/amm/test_amm_enums.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_amm_enums.py
"""Test AMM-specific enums."""
from src.amm.models.enums import DefenseLevel, Phase, QuoteAction


class TestDefenseLevel:
    def test_escalation_order(self) -> None:
        levels = list(DefenseLevel)
        assert levels == [
            DefenseLevel.NORMAL,
            DefenseLevel.WIDEN,
            DefenseLevel.ONE_SIDE,
            DefenseLevel.KILL_SWITCH,
        ]

    def test_is_active(self) -> None:
        assert DefenseLevel.NORMAL.is_quoting_active is True
        assert DefenseLevel.WIDEN.is_quoting_active is True
        assert DefenseLevel.ONE_SIDE.is_quoting_active is True
        assert DefenseLevel.KILL_SWITCH.is_quoting_active is False


class TestPhase:
    def test_phases(self) -> None:
        assert Phase.EXPLORATION.value == "EXPLORATION"
        assert Phase.STABILIZATION.value == "STABILIZATION"


class TestQuoteAction:
    def test_actions(self) -> None:
        assert QuoteAction.PLACE.value == "PLACE"
        assert QuoteAction.REPLACE.value == "REPLACE"
        assert QuoteAction.CANCEL.value == "CANCEL"
        assert QuoteAction.HOLD.value == "HOLD"
```

**Step 2: Run to verify FAIL**
```bash
uv run pytest tests/unit/amm/test_amm_enums.py -v
```

**Step 3: Implement**

```python
# src/amm/models/enums.py
"""AMM-specific enumerations."""
from enum import StrEnum


class DefenseLevel(StrEnum):
    """Risk defense escalation levels. Order matters — higher = more restrictive."""
    NORMAL = "NORMAL"
    WIDEN = "WIDEN"
    ONE_SIDE = "ONE_SIDE"
    KILL_SWITCH = "KILL_SWITCH"

    @property
    def is_quoting_active(self) -> bool:
        return self != DefenseLevel.KILL_SWITCH


class Phase(StrEnum):
    """AMM strategy phases."""
    EXPLORATION = "EXPLORATION"
    STABILIZATION = "STABILIZATION"


class QuoteAction(StrEnum):
    """Order intent actions from strategy layer."""
    PLACE = "PLACE"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"
    HOLD = "HOLD"
```

Create `__init__.py` files for all new directories:
```bash
mkdir -p src/amm/models src/amm/config src/amm/connector src/amm/strategy/pricing src/amm/risk src/amm/lifecycle src/amm/cache src/amm/utils
touch src/amm/__init__.py src/amm/models/__init__.py src/amm/config/__init__.py src/amm/connector/__init__.py src/amm/strategy/__init__.py src/amm/strategy/pricing/__init__.py src/amm/risk/__init__.py src/amm/lifecycle/__init__.py src/amm/cache/__init__.py src/amm/utils/__init__.py
mkdir -p tests/unit/amm tests/integration/amm
touch tests/unit/amm/__init__.py tests/integration/amm/__init__.py
```

**Step 4: Run to verify PASS**
```bash
uv run pytest tests/unit/amm/test_amm_enums.py -v
```

**Step 5: Commit**
```bash
git add src/amm/ tests/unit/amm/
git commit -m "feat(amm): add project scaffolding and AMM enums"
```

---

## Task 2: Integer Math Utilities

**Files:**
- Create: `src/amm/utils/integer_math.py`
- Test: `tests/unit/amm/test_integer_math.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_integer_math.py
"""Integer-only math for AMM. No floats in financial calculations."""
import pytest
from src.amm.utils.integer_math import ceiling_div, calculate_fee, clamp


class TestCeilingDiv:
    def test_exact_division(self) -> None:
        assert ceiling_div(100, 10) == 10

    def test_rounds_up(self) -> None:
        assert ceiling_div(101, 10) == 11

    def test_one(self) -> None:
        assert ceiling_div(1, 10000) == 1  # 1/10000 rounds up to 1


class TestCalculateFee:
    def test_standard_fee(self) -> None:
        # trade_value=6500, bps=20 → 6500*20/10000 = 13 → ceiling = 13
        assert calculate_fee(6500, 20) == 13

    def test_ceiling_behavior(self) -> None:
        # trade_value=100, bps=20 → 100*20=2000 → (2000+9999)//10000 = 1
        assert calculate_fee(100, 20) == 1

    def test_zero_value(self) -> None:
        assert calculate_fee(0, 20) == 0


class TestClamp:
    def test_within_range(self) -> None:
        assert clamp(50, 1, 99) == 50

    def test_below_min(self) -> None:
        assert clamp(0, 1, 99) == 1

    def test_above_max(self) -> None:
        assert clamp(100, 1, 99) == 99
```

**Step 2: Run to verify FAIL**

**Step 3: Implement**

```python
# src/amm/utils/integer_math.py
"""Integer-safe mathematical operations for AMM.

All financial calculations MUST use integer arithmetic to avoid
floating-point precision issues. Prices in cents [1, 99].
"""


def ceiling_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division: ⌈a/b⌉. Always rounds UP."""
    if numerator == 0:
        return 0
    return (numerator + denominator - 1) // denominator


def calculate_fee(trade_value_cents: int, fee_bps: int) -> int:
    """Calculate fee with ceiling rounding. Formula: ⌈value × bps / 10000⌉.

    Aligned with pm_clearing fee formula.
    """
    if trade_value_cents == 0:
        return 0
    return (trade_value_cents * fee_bps + 9999) // 10000


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Clamp value to [minimum, maximum] range."""
    return max(minimum, min(value, maximum))
```

**Step 4: Run to verify PASS + Commit**

---

## Task 3: Inventory & MarketContext Data Models

**Files:**
- Create: `src/amm/models/inventory.py`
- Create: `src/amm/models/market_context.py`
- Test: `tests/unit/amm/test_market_context.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_market_context.py
from src.amm.models.inventory import Inventory


class TestInventory:
    def test_yes_available(self) -> None:
        inv = Inventory(cash_cents=100000, yes_volume=500, no_volume=500,
                        yes_cost_sum_cents=25000, no_cost_sum_cents=25000,
                        yes_pending_sell=100, no_pending_sell=50, frozen_balance_cents=0)
        assert inv.yes_available == 400

    def test_no_available(self) -> None:
        inv = Inventory(cash_cents=100000, yes_volume=500, no_volume=500,
                        yes_cost_sum_cents=25000, no_cost_sum_cents=25000,
                        yes_pending_sell=100, no_pending_sell=50, frozen_balance_cents=0)
        assert inv.no_available == 450

    def test_inventory_skew_balanced(self) -> None:
        inv = Inventory(cash_cents=100000, yes_volume=500, no_volume=500,
                        yes_cost_sum_cents=25000, no_cost_sum_cents=25000,
                        yes_pending_sell=0, no_pending_sell=0, frozen_balance_cents=0)
        assert inv.inventory_skew == 0.0

    def test_inventory_skew_positive(self) -> None:
        inv = Inventory(cash_cents=100000, yes_volume=800, no_volume=200,
                        yes_cost_sum_cents=40000, no_cost_sum_cents=10000,
                        yes_pending_sell=0, no_pending_sell=0, frozen_balance_cents=0)
        assert inv.inventory_skew == pytest.approx(0.6)

    def test_inventory_skew_empty(self) -> None:
        inv = Inventory(cash_cents=100000, yes_volume=0, no_volume=0,
                        yes_cost_sum_cents=0, no_cost_sum_cents=0,
                        yes_pending_sell=0, no_pending_sell=0, frozen_balance_cents=0)
        assert inv.inventory_skew == 0.0

    def test_total_value_cents(self) -> None:
        """Total portfolio value = cash + yes_volume × mid + no_volume × (100 - mid)."""
        inv = Inventory(cash_cents=100000, yes_volume=100, no_volume=100,
                        yes_cost_sum_cents=5000, no_cost_sum_cents=5000,
                        yes_pending_sell=0, no_pending_sell=0, frozen_balance_cents=0)
        # At mid_price=50: 100000 + 100*50 + 100*50 = 110000
        assert inv.total_value_cents(mid_price_cents=50) == 110000
```

**Step 2: Implement**

```python
# src/amm/models/inventory.py
"""AMM inventory model. All values in integer cents/shares."""
from dataclasses import dataclass


@dataclass
class Inventory:
    cash_cents: int
    yes_volume: int
    no_volume: int
    yes_cost_sum_cents: int
    no_cost_sum_cents: int
    yes_pending_sell: int
    no_pending_sell: int
    frozen_balance_cents: int

    @property
    def yes_available(self) -> int:
        return self.yes_volume - self.yes_pending_sell

    @property
    def no_available(self) -> int:
        return self.no_volume - self.no_pending_sell

    @property
    def inventory_skew(self) -> float:
        """q = (yes - no) / (yes + no). Range [-1, 1]."""
        total = self.yes_volume + self.no_volume
        if total == 0:
            return 0.0
        return (self.yes_volume - self.no_volume) / total

    def total_value_cents(self, mid_price_cents: int) -> int:
        """Total portfolio value in cents."""
        yes_value = self.yes_volume * mid_price_cents
        no_value = self.no_volume * (100 - mid_price_cents)
        return self.cash_cents + yes_value + no_value + self.frozen_balance_cents
```

**Step 3: Implement MarketContext** (see design doc §4.1 for full definition)

**Step 4: Run to verify PASS + Commit**

---

## Task 4: Configuration System

**Files:**
- Create: `src/amm/config/models.py`
- Create: `src/amm/config/loader.py`
- Create: `src/amm/config/default.yaml`
- Test: `tests/unit/amm/test_config_loader.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_config_loader.py
import pytest
from src.amm.config.models import GlobalConfig, MarketConfig


class TestGlobalConfig:
    def test_defaults(self) -> None:
        cfg = GlobalConfig()
        assert cfg.quote_interval_seconds == 2.0
        assert cfg.reconcile_interval_seconds == 300.0
        assert cfg.base_url == "http://localhost:8000/api/v1"

    def test_redis_override(self) -> None:
        """Redis values should override YAML defaults."""
        cfg = GlobalConfig()
        cfg.quote_interval_seconds = 1.0
        assert cfg.quote_interval_seconds == 1.0


class TestMarketConfig:
    def test_market_defaults(self) -> None:
        cfg = MarketConfig(market_id="mkt-1")
        assert cfg.gamma_tier == "MID"
        assert cfg.initial_mint_quantity == 1000
        assert cfg.max_daily_loss_cents == 100_00  # $100
        assert cfg.spread_min_cents == 2
        assert cfg.gradient_levels == 3

    def test_gamma_value(self) -> None:
        cfg = MarketConfig(market_id="mkt-1", gamma_tier="EARLY")
        assert cfg.gamma == 0.1

        cfg2 = MarketConfig(market_id="mkt-1", gamma_tier="LATE")
        assert cfg2.gamma == 0.8
```

**Step 2: Implement models**

```python
# src/amm/config/models.py
"""AMM configuration models. Aligned with config handbook v1.3."""
from dataclasses import dataclass, field

GAMMA_TIERS: dict[str, float] = {
    "EARLY": 0.1,
    "MID": 0.3,
    "LATE": 0.8,
    "MATURE": 1.5,
}


@dataclass
class GlobalConfig:
    """Global AMM settings (not per-market)."""
    base_url: str = "http://localhost:8000/api/v1"
    redis_url: str = "redis://localhost:6379/0"
    amm_username: str = "amm_market_maker"
    amm_password: str = ""  # from env var, never in YAML

    quote_interval_seconds: float = 2.0
    reconcile_interval_seconds: float = 300.0
    trade_poll_interval_seconds: float = 2.0
    balance_poll_interval_seconds: float = 30.0

    max_concurrent_markets: int = 50
    log_level: str = "INFO"


@dataclass
class MarketConfig:
    """Per-market AMM configuration. 87+ parameters."""
    market_id: str

    # Pricing
    gamma_tier: str = "MID"
    kappa: float = 1.5               # market depth / order arrival intensity
    anchor_price_cents: int = 50     # initial anchor price
    spread_min_cents: int = 2        # minimum spread
    spread_max_cents: int = 20       # maximum spread

    # Inventory
    initial_mint_quantity: int = 1000
    auto_reinvest_enabled: bool = True
    auto_merge_threshold: float = 0.3  # merge when skew drops below this

    # Gradient
    gradient_levels: int = 3          # number of price levels per side
    gradient_quantity_decay: float = 0.5  # each level has 50% of previous
    gradient_price_step_cents: int = 1    # price step between levels

    # Risk
    max_daily_loss_cents: int = 100_00    # $100
    max_per_market_loss_cents: int = 50_00  # $50
    inventory_skew_widen: float = 0.3      # trigger WIDEN
    inventory_skew_one_side: float = 0.6   # trigger ONE_SIDE
    inventory_skew_kill: float = 0.8       # trigger KILL_SWITCH
    widen_factor: float = 1.5              # spread multiplier in WIDEN mode
    defense_cooldown_cycles: int = 5       # cycles before de-escalation

    # Phase
    exploration_duration_hours: float = 24.0
    stabilization_volume_threshold: int = 100  # trades to trigger STABILIZATION

    # Timing
    remaining_hours_override: float | None = None  # for testing

    @property
    def gamma(self) -> float:
        return GAMMA_TIERS.get(self.gamma_tier, 0.3)
```

**Step 3: Implement YAML loader + Redis overlay** (in `loader.py`)

**Step 4: Create `default.yaml`** with all 87+ parameters

**Step 5: Run to verify PASS + Commit**

---

## Task 5: Redis Cache Layer

**Files:**
- Create: `src/amm/cache/redis_client.py`
- Create: `src/amm/cache/inventory_cache.py`
- Create: `src/amm/cache/order_cache.py`
- Test: `tests/unit/amm/test_inventory_cache.py` (using fakeredis)

**Step 1: Write tests** using `fakeredis.aioredis` for unit testing

**Step 2: Implement inventory_cache** — CRUD for `amm:inventory:{market_id}` Hash

**Step 3: Implement order_cache** — CRUD for `amm:orders:{market_id}` Hash

**Step 4: Run to verify PASS + Commit**

---

## Task 6: API Client + Token Management

**Files:**
- Create: `src/amm/connector/api_client.py`
- Create: `src/amm/connector/auth.py`
- Test: `tests/unit/amm/test_api_client.py` (using respx for HTTP mocking)

**Step 1: Write failing test**

```python
# tests/unit/amm/test_api_client.py (outline)
class TestAMMApiClient:
    async def test_login_obtains_tokens(self) -> None: ...
    async def test_auto_refresh_on_401(self) -> None: ...
    async def test_place_order(self) -> None: ...
    async def test_cancel_order(self) -> None: ...
    async def test_replace_order(self) -> None: ...
    async def test_mint(self) -> None: ...
    async def test_burn(self) -> None: ...
    async def test_get_balance(self) -> None: ...
    async def test_get_positions(self) -> None: ...
    async def test_rate_limit_backoff(self) -> None: ...
```

**Step 2: Implement**

```python
# src/amm/connector/api_client.py
"""REST API client for AMM ↔ matching engine communication."""
import logging
import httpx
from src.amm.connector.auth import TokenManager

logger = logging.getLogger(__name__)


class AMMApiClient:
    def __init__(self, base_url: str, token_manager: TokenManager):
        self._base_url = base_url
        self._token_manager = token_manager
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request with auto-retry on 401."""
        headers = {"Authorization": f"Bearer {self._token_manager.access_token}"}
        resp = await self._client.request(method, path, headers=headers, **kwargs)

        if resp.status_code == 401:
            await self._token_manager.refresh()
            headers["Authorization"] = f"Bearer {self._token_manager.access_token}"
            resp = await self._client.request(method, path, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp.json()

    async def place_order(self, params: dict) -> dict:
        return await self._request("POST", "/orders", json=params)

    async def cancel_order(self, order_id: str) -> dict:
        return await self._request("POST", f"/orders/{order_id}/cancel")

    async def replace_order(self, old_order_id: str, new_order: dict) -> dict:
        return await self._request("POST", "/amm/orders/replace",
                                   json={"old_order_id": old_order_id, "new_order": new_order})

    async def batch_cancel(self, market_id: str, scope: str = "ALL") -> dict:
        return await self._request("POST", "/amm/orders/batch-cancel",
                                   json={"market_id": market_id, "cancel_scope": scope})

    async def mint(self, market_id: str, quantity: int, key: str) -> dict:
        return await self._request("POST", "/amm/mint",
                                   json={"market_id": market_id, "quantity": quantity,
                                         "idempotency_key": key})

    async def burn(self, market_id: str, quantity: int, key: str) -> dict:
        return await self._request("POST", "/amm/burn",
                                   json={"market_id": market_id, "quantity": quantity,
                                         "idempotency_key": key})

    async def get_balance(self) -> dict:
        return await self._request("GET", "/account/balance")

    async def get_positions(self, market_id: str) -> dict:
        return await self._request("GET", f"/positions/{market_id}")

    async def get_trades(self, cursor: str = "", limit: int = 50) -> dict:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/trades", params=params)

    async def get_market(self, market_id: str) -> dict:
        return await self._request("GET", f"/markets/{market_id}")

    async def close(self) -> None:
        await self._client.aclose()
```

**Step 3: Implement TokenManager** in `auth.py`

**Step 4: Run to verify PASS + Commit**

---

## Task 7: Trade Poller + Inventory Sync

**Files:**
- Create: `src/amm/connector/trade_poller.py`
- Create: `src/amm/connector/inventory_sync.py`
- Test: `tests/unit/amm/test_inventory_sync.py`

**Step 1: Write test**

```python
# tests/unit/amm/test_inventory_sync.py (outline)
class TestTradePoller:
    async def test_poll_incremental_updates_redis(self) -> None: ...
    async def test_poll_deduplicates_trades(self) -> None: ...
    async def test_poll_updates_cursor(self) -> None: ...
    async def test_trade_buy_yes_increases_yes_volume(self) -> None: ...
    async def test_trade_sell_yes_decreases_yes_volume(self) -> None: ...
    async def test_mint_trade_increases_both(self) -> None: ...
    async def test_burn_trade_decreases_both(self) -> None: ...
```

**Step 2: Implement trade_poller**

```python
# src/amm/connector/trade_poller.py
"""Poll trades endpoint to sync AMM inventory into Redis.

MVP alternative to Kafka trade_events. See interface contract v1.4 §5.1.
"""
import logging
from src.amm.connector.api_client import AMMApiClient
from src.amm.cache.inventory_cache import InventoryCache

logger = logging.getLogger(__name__)


class TradePoller:
    def __init__(self, api: AMMApiClient, cache: InventoryCache):
        self._api = api
        self._cache = cache
        self._cursors: dict[str, str] = {}  # market_id → last trade cursor
        self._processed_ids: set[str] = set()  # deduplication

    async def poll(self, market_id: str) -> int:
        """Poll for new trades, update Redis inventory. Returns count of new trades."""
        cursor = self._cursors.get(market_id, "")
        resp = await self._api.get_trades(cursor=cursor, limit=50)
        trades = resp.get("data", {}).get("trades", [])

        new_count = 0
        for trade in trades:
            trade_id = trade["id"]
            if trade_id in self._processed_ids:
                continue

            self._processed_ids.add(trade_id)
            await self._apply_trade(market_id, trade)
            new_count += 1

        if trades:
            self._cursors[market_id] = trades[-1]["id"]

        return new_count

    async def _apply_trade(self, market_id: str, trade: dict) -> None:
        """Update Redis inventory based on a single trade."""
        from src.pm_account.domain.constants import AMM_USER_ID

        scenario = trade["scenario"]
        quantity = trade["quantity"]
        price = trade["price_cents"]
        is_buyer = trade["buy_user_id"] == AMM_USER_ID

        if scenario == "MINT":
            await self._cache.adjust(market_id, yes_delta=quantity, no_delta=quantity,
                                     cash_delta=-(quantity * 100))
        elif scenario == "BURN":
            await self._cache.adjust(market_id, yes_delta=-quantity, no_delta=-quantity,
                                     cash_delta=quantity * 100)
        elif scenario == "TRANSFER_YES":
            if is_buyer:
                await self._cache.adjust(market_id, yes_delta=quantity,
                                         cash_delta=-(price * quantity))
            else:
                await self._cache.adjust(market_id, yes_delta=-quantity,
                                         cash_delta=price * quantity)
        elif scenario == "TRANSFER_NO":
            if is_buyer:
                await self._cache.adjust(market_id, no_delta=quantity,
                                         cash_delta=-((100 - price) * quantity))
            else:
                await self._cache.adjust(market_id, no_delta=-quantity,
                                         cash_delta=(100 - price) * quantity)
```

**Step 3: Run to verify PASS + Commit**

---

## Task 8: Three-Layer Pricing Engine

**Files:**
- Create: `src/amm/strategy/pricing/three_layer.py`
- Create: `src/amm/strategy/pricing/anchor.py`
- Create: `src/amm/strategy/pricing/micro.py`
- Create: `src/amm/strategy/pricing/posterior.py`
- Test: `tests/unit/amm/test_three_layer_pricing.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_three_layer_pricing.py
"""Test three-layer pricing engine. See AMM design v7.1 §3."""
import pytest
from src.amm.strategy.pricing.three_layer import ThreeLayerPricing
from src.amm.strategy.pricing.anchor import AnchorPricing
from src.amm.strategy.pricing.micro import MicroPricing
from src.amm.strategy.pricing.posterior import PosteriorPricing


class TestThreeLayerPricing:
    def test_exploration_phase_anchor_dominant(self) -> None:
        """In EXPLORATION, anchor weight is highest."""
        engine = ThreeLayerPricing(
            anchor=AnchorPricing(initial_price=50),
            micro=MicroPricing(),
            posterior=PosteriorPricing(),
        )
        mid = engine.compute(
            phase="EXPLORATION",
            anchor_price=50,
            best_bid=48,
            best_ask=52,
            recent_trades=[],
        )
        assert mid == 50  # anchor dominates

    def test_stabilization_phase_micro_weight_increases(self) -> None:
        """In STABILIZATION, micro-price gets more weight."""
        engine = ThreeLayerPricing(
            anchor=AnchorPricing(initial_price=50),
            micro=MicroPricing(),
            posterior=PosteriorPricing(),
        )
        mid = engine.compute(
            phase="STABILIZATION",
            anchor_price=50,
            best_bid=55,
            best_ask=57,
            recent_trades=[{"price_cents": 56, "quantity": 10}],
        )
        # Should shift toward 56 (micro/posterior influence)
        assert 50 < mid < 57

    def test_output_clamped_to_valid_range(self) -> None:
        """Output must be in [1, 99]."""
        engine = ThreeLayerPricing(
            anchor=AnchorPricing(initial_price=99),
            micro=MicroPricing(),
            posterior=PosteriorPricing(),
        )
        mid = engine.compute(
            phase="EXPLORATION",
            anchor_price=99,
            best_bid=98,
            best_ask=100,  # invalid, but test robustness
            recent_trades=[],
        )
        assert 1 <= mid <= 99
```

**Step 2: Implement**

```python
# src/amm/strategy/pricing/three_layer.py
"""Three-layer pricing engine. See AMM design v7.1 §3.

Layer 1: Anchor price (admin-set or initial probability)
Layer 2: Micro-structure price (mid-price, VWAP, anti-spoofing)
Layer 3: Posterior learning (Bayesian update from trade flow)

Weights shift from anchor-dominant (EXPLORATION) to micro-dominant (STABILIZATION).
"""
from src.amm.utils.integer_math import clamp

# Phase-dependent weights: (anchor, micro, posterior)
PHASE_WEIGHTS = {
    "EXPLORATION": (0.6, 0.3, 0.1),
    "STABILIZATION": (0.2, 0.5, 0.3),
}


class ThreeLayerPricing:
    def __init__(self, anchor, micro, posterior):
        self._anchor = anchor
        self._micro = micro
        self._posterior = posterior

    def compute(
        self,
        phase: str,
        anchor_price: int,
        best_bid: int,
        best_ask: int,
        recent_trades: list[dict],
    ) -> int:
        """Compute mid-price as weighted combination of three layers."""
        w_a, w_m, w_p = PHASE_WEIGHTS.get(phase, PHASE_WEIGHTS["EXPLORATION"])

        p_anchor = self._anchor.compute(anchor_price)
        p_micro = self._micro.compute(best_bid, best_ask)
        p_posterior = self._posterior.compute(recent_trades, fallback=p_anchor)

        raw = w_a * p_anchor + w_m * p_micro + w_p * p_posterior
        return clamp(round(raw), 1, 99)
```

**Step 3: Implement anchor.py, micro.py, posterior.py**

**Step 4: Run to verify PASS + Commit**

---

## Task 9: Avellaneda-Stoikov Engine

**Files:**
- Create: `src/amm/strategy/as_engine.py`
- Test: `tests/unit/amm/test_as_engine.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_as_engine.py
"""Test A-S reservation price and optimal spread. See AMM design v7.1 §5."""
import pytest
import math
from src.amm.strategy.as_engine import ASEngine


class TestASEngine:
    def test_reservation_price_balanced_inventory(self) -> None:
        """q=0 → r = s (no inventory adjustment)."""
        engine = ASEngine()
        r = engine.reservation_price(
            mid_price=50, inventory_skew=0.0, gamma=0.3, sigma=0.05, tau_hours=24.0
        )
        assert r == pytest.approx(50.0, abs=0.01)

    def test_reservation_price_long_yes(self) -> None:
        """Positive skew (long YES) → r < s (lower to encourage selling YES)."""
        engine = ASEngine()
        r = engine.reservation_price(
            mid_price=50, inventory_skew=0.5, gamma=0.3, sigma=0.05, tau_hours=24.0
        )
        assert r < 50.0

    def test_reservation_price_long_no(self) -> None:
        """Negative skew (long NO) → r > s (higher to encourage selling NO)."""
        engine = ASEngine()
        r = engine.reservation_price(
            mid_price=50, inventory_skew=-0.5, gamma=0.3, sigma=0.05, tau_hours=24.0
        )
        assert r > 50.0

    def test_optimal_spread_positive(self) -> None:
        """Spread must always be positive."""
        engine = ASEngine()
        delta = engine.optimal_spread(gamma=0.3, sigma=0.05, tau_hours=24.0, kappa=1.5)
        assert delta > 0

    def test_spread_increases_with_gamma(self) -> None:
        """Higher gamma (more risk averse) → wider spread."""
        engine = ASEngine()
        d1 = engine.optimal_spread(gamma=0.1, sigma=0.05, tau_hours=24.0, kappa=1.5)
        d2 = engine.optimal_spread(gamma=0.8, sigma=0.05, tau_hours=24.0, kappa=1.5)
        assert d2 > d1

    def test_sigma_bernoulli(self) -> None:
        """σ = sqrt(p(1-p)) / 100 for binary outcome."""
        engine = ASEngine()
        sigma = engine.bernoulli_sigma(mid_price_cents=50)
        expected = math.sqrt(0.5 * 0.5) / 100  # = 0.005
        assert sigma == pytest.approx(expected, rel=1e-6)

    def test_sigma_at_extremes(self) -> None:
        """At p=1 or p=99, sigma is very small."""
        engine = ASEngine()
        sigma_low = engine.bernoulli_sigma(mid_price_cents=1)
        sigma_high = engine.bernoulli_sigma(mid_price_cents=99)
        assert sigma_low < 0.01
        assert sigma_high < 0.01

    def test_gamma_tier_lookup(self) -> None:
        engine = ASEngine()
        assert engine.get_gamma("EARLY") == 0.1
        assert engine.get_gamma("MID") == 0.3
        assert engine.get_gamma("LATE") == 0.8
        assert engine.get_gamma("MATURE") == 1.5

    def test_quote_prices(self) -> None:
        """Full quote: ask > bid, both in [1, 99]."""
        engine = ASEngine()
        ask, bid = engine.compute_quotes(
            mid_price=50, inventory_skew=0.0, gamma=0.3,
            sigma=0.05, tau_hours=24.0, kappa=1.5,
        )
        assert 1 <= bid < ask <= 99
```

**Step 2: Implement**

```python
# src/amm/strategy/as_engine.py
"""Avellaneda-Stoikov pricing model adapted for prediction markets.

See AMM design v7.1 §5:
  r = s - q · γ · σ² · τ(h)
  δ = γ · σ² · τ(h) + (2/γ) · ln(1 + γ/κ)

Key adaptations for prediction markets:
- σ uses Bernoulli: σ = sqrt(p(1-p)) / 100 (binary outcome)
- τ is absolute hours remaining (not fraction of day)
- γ is lifecycle-stratified (EARLY/MID/LATE/MATURE)
- All final prices clamped to [1, 99] integer cents
"""
import math
from src.amm.config.models import GAMMA_TIERS
from src.amm.utils.integer_math import clamp


class ASEngine:
    def reservation_price(
        self, mid_price: float, inventory_skew: float,
        gamma: float, sigma: float, tau_hours: float,
    ) -> float:
        """r = s - q · γ · σ² · τ(h)"""
        return mid_price - inventory_skew * gamma * (sigma ** 2) * tau_hours

    def optimal_spread(
        self, gamma: float, sigma: float, tau_hours: float, kappa: float,
    ) -> float:
        """δ = γ · σ² · τ(h) + (2/γ) · ln(1 + γ/κ)"""
        inventory_component = gamma * (sigma ** 2) * tau_hours
        depth_component = (2.0 / gamma) * math.log(1.0 + gamma / kappa)
        return inventory_component + depth_component

    def bernoulli_sigma(self, mid_price_cents: int) -> float:
        """σ = sqrt(p(1-p)) / 100 for binary prediction market."""
        p = mid_price_cents / 100.0
        p = max(0.01, min(0.99, p))  # avoid zero variance
        return math.sqrt(p * (1 - p)) / 100.0

    def get_gamma(self, tier: str) -> float:
        return GAMMA_TIERS.get(tier, 0.3)

    def compute_quotes(
        self, mid_price: int, inventory_skew: float,
        gamma: float, sigma: float, tau_hours: float, kappa: float,
    ) -> tuple[int, int]:
        """Compute ask and bid prices. Returns (ask_cents, bid_cents)."""
        r = self.reservation_price(mid_price, inventory_skew, gamma, sigma, tau_hours)
        delta = self.optimal_spread(gamma, sigma, tau_hours, kappa)

        ask_raw = r + delta / 2
        bid_raw = r - delta / 2

        ask = clamp(round(ask_raw), 1, 99)
        bid = clamp(round(bid_raw), 1, 99)

        # Ensure positive spread
        if ask <= bid:
            ask = min(bid + 1, 99)

        return ask, bid
```

**Step 3: Run to verify PASS + Commit**

---

## Task 10: Gradient Engine

**Files:**
- Create: `src/amm/strategy/gradient.py`
- Test: `tests/unit/amm/test_gradient.py`

**Step 1: Write test** — build_ask_ladder, build_bid_ladder with decay and price steps

**Step 2: Implement** — generate multi-level order ladders from base ask/bid

**Step 3: Run to verify PASS + Commit**

---

## Task 11: Phase Manager

**Files:**
- Create: `src/amm/strategy/phase_manager.py`
- Test: `tests/unit/amm/test_phase_manager.py`

**Step 1: Write test** — EXPLORATION → STABILIZATION transition, reverse transition, debounce

**Step 2: Implement** — state machine with configurable transition thresholds

**Step 3: Run to verify PASS + Commit**

---

## Task 12: Defense Stack (Three Lines of Defense)

**Files:**
- Create: `src/amm/risk/defense_stack.py`
- Test: `tests/unit/amm/test_defense_stack.py`

**Step 1: Write failing test**

```python
# tests/unit/amm/test_defense_stack.py
"""Test three-line defense escalation. See AMM design v7.1 §10."""
import pytest
from src.amm.risk.defense_stack import DefenseStack
from src.amm.models.enums import DefenseLevel
from src.amm.config.models import MarketConfig


class TestDefenseStack:
    def test_normal_state(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1"))
        level = ds.evaluate(inventory_skew=0.1, daily_pnl=-100, market_active=True)
        assert level == DefenseLevel.NORMAL

    def test_widen_on_skew(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1", inventory_skew_widen=0.3))
        level = ds.evaluate(inventory_skew=0.4, daily_pnl=-100, market_active=True)
        assert level == DefenseLevel.WIDEN

    def test_one_side_on_high_skew(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1", inventory_skew_one_side=0.6))
        level = ds.evaluate(inventory_skew=0.7, daily_pnl=-100, market_active=True)
        assert level == DefenseLevel.ONE_SIDE

    def test_kill_switch_on_extreme_skew(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1", inventory_skew_kill=0.8))
        level = ds.evaluate(inventory_skew=0.9, daily_pnl=-100, market_active=True)
        assert level == DefenseLevel.KILL_SWITCH

    def test_kill_switch_on_budget_breach(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1", max_daily_loss_cents=10000))
        level = ds.evaluate(inventory_skew=0.1, daily_pnl=-15000, market_active=True)
        assert level == DefenseLevel.KILL_SWITCH

    def test_kill_switch_on_market_inactive(self) -> None:
        ds = DefenseStack(MarketConfig(market_id="mkt-1"))
        level = ds.evaluate(inventory_skew=0.0, daily_pnl=0, market_active=False)
        assert level == DefenseLevel.KILL_SWITCH

    def test_de_escalation_requires_cooldown(self) -> None:
        """Must stay at lower level for N cycles before de-escalating."""
        ds = DefenseStack(MarketConfig(market_id="mkt-1", defense_cooldown_cycles=3))
        # Escalate to WIDEN
        ds.evaluate(inventory_skew=0.4, daily_pnl=0, market_active=True)
        assert ds.current_level == DefenseLevel.WIDEN

        # Conditions improve, but need 3 cycles of cooldown
        ds.evaluate(inventory_skew=0.1, daily_pnl=0, market_active=True)
        assert ds.current_level == DefenseLevel.WIDEN  # still WIDEN (1/3)
        ds.evaluate(inventory_skew=0.1, daily_pnl=0, market_active=True)
        assert ds.current_level == DefenseLevel.WIDEN  # (2/3)
        ds.evaluate(inventory_skew=0.1, daily_pnl=0, market_active=True)
        assert ds.current_level == DefenseLevel.NORMAL  # de-escalated after 3 cycles
```

**Step 2: Implement**

```python
# src/amm/risk/defense_stack.py
"""Three-line defense system. See AMM design v7.1 §10."""
import logging
from src.amm.models.enums import DefenseLevel
from src.amm.config.models import MarketConfig

logger = logging.getLogger(__name__)


class DefenseStack:
    def __init__(self, config: MarketConfig):
        self._config = config
        self.current_level = DefenseLevel.NORMAL
        self._cooldown_counter = 0

    def evaluate(
        self, inventory_skew: float, daily_pnl: int, market_active: bool,
    ) -> DefenseLevel:
        """Evaluate current market conditions and return defense level."""
        target = self._determine_target(inventory_skew, daily_pnl, market_active)

        if target.value > self.current_level.value:
            # Escalation is immediate
            self.current_level = target
            self._cooldown_counter = 0
            logger.warning("Defense ESCALATED to %s (skew=%.2f, pnl=%d)",
                           target, inventory_skew, daily_pnl)
        elif target.value < self.current_level.value:
            # De-escalation requires cooldown
            self._cooldown_counter += 1
            if self._cooldown_counter >= self._config.defense_cooldown_cycles:
                self.current_level = target
                self._cooldown_counter = 0
                logger.info("Defense de-escalated to %s", target)
        else:
            self._cooldown_counter = 0

        return self.current_level

    def _determine_target(
        self, skew: float, pnl: int, active: bool,
    ) -> DefenseLevel:
        abs_skew = abs(skew)

        if not active:
            return DefenseLevel.KILL_SWITCH
        if abs_skew >= self._config.inventory_skew_kill:
            return DefenseLevel.KILL_SWITCH
        if pnl <= -self._config.max_per_market_loss_cents:
            return DefenseLevel.KILL_SWITCH
        if abs_skew >= self._config.inventory_skew_one_side:
            return DefenseLevel.ONE_SIDE
        if pnl <= -(self._config.max_per_market_loss_cents // 2):
            return DefenseLevel.ONE_SIDE
        if abs_skew >= self._config.inventory_skew_widen:
            return DefenseLevel.WIDEN
        return DefenseLevel.NORMAL
```

**Step 3: Run to verify PASS + Commit**

---

## Task 13: Budget Manager

**Files:**
- Create: `src/amm/risk/budget_manager.py`
- Test: `tests/unit/amm/test_budget_manager.py`

**Step 1: Write test** — daily P&L tracking, per-market tracking, budget breach detection

**Step 2: Implement** — P&L calculation from inventory snapshots

**Step 3: Run to verify PASS + Commit**

---

## Task 14: Order Sanitizer

**Files:**
- Create: `src/amm/risk/sanitizer.py`
- Test: `tests/unit/amm/test_sanitizer.py`

**Step 1: Write test** — price clamping [1,99], quantity limits, negative spread rejection

**Step 2: Implement** — validate and fix OrderIntent before execution

**Step 3: Run to verify PASS + Commit**

---

## Task 15: Order Manager

**Files:**
- Create: `src/amm/connector/order_manager.py`
- Test: `tests/unit/amm/test_order_manager.py`

**Step 1: Write test** — diff calculation (current vs target orders), replace/place/cancel decisions

**Step 2: Implement** — smart order diffing to minimize API calls

```python
# src/amm/connector/order_manager.py (outline)
class OrderManager:
    async def execute_intents(self, intents: list[OrderIntent], market_id: str) -> None:
        """Execute order intents by comparing with current active orders.

        Strategy:
        1. For REPLACE: use atomic replace API
        2. For new orders with no matching active: place new
        3. For stale active orders not in intents: cancel
        """
        ...

    def _compute_diff(
        self, active: dict[str, ActiveOrder], target: list[OrderIntent],
    ) -> tuple[list[ReplaceAction], list[PlaceAction], list[CancelAction]]:
        """Compute minimum actions to transform current state to target state."""
        ...
```

**Step 3: Run to verify PASS + Commit**

---

## Task 16: Lifecycle — Initializer

**Files:**
- Create: `src/amm/lifecycle/initializer.py`
- Test: `tests/unit/amm/test_initializer.py`

**Step 1: Write test** — startup sequence: login → load config → fetch balance → fetch positions → build Redis → initial mint if needed

**Step 2: Implement**

```python
# src/amm/lifecycle/initializer.py (outline)
class AMMInitializer:
    async def initialize(self, market_ids: list[str]) -> dict[str, MarketContext]:
        """Full AMM startup sequence."""
        # 1. Login (get JWT tokens)
        await self._token_manager.login()

        # 2. Load config (YAML + Redis)
        global_config = await self._config_loader.load_global()

        contexts = {}
        for market_id in market_ids:
            # 3. Load market config
            market_config = await self._config_loader.load_market(market_id)

            # 4. Fetch current state from DB (via API)
            balance = await self._api.get_balance()
            positions = await self._api.get_positions(market_id)
            market = await self._api.get_market(market_id)

            # 5. Build inventory from DB state
            inventory = self._build_inventory(balance, positions)

            # 6. Write to Redis cache
            await self._inventory_cache.set(market_id, inventory)

            # 7. Initial mint if no positions
            if inventory.yes_volume == 0 and inventory.no_volume == 0:
                await self._api.mint(
                    market_id, market_config.initial_mint_quantity,
                    f"init_{market_id}_{int(time.time())}"
                )
                # Re-fetch inventory
                ...

            # 8. Create MarketContext
            ctx = MarketContext(market_id=market_id, config=market_config, ...)
            contexts[market_id] = ctx

        return contexts
```

**Step 3: Run to verify PASS + Commit**

---

## Task 17: Lifecycle — Reconciler

**Files:**
- Create: `src/amm/lifecycle/reconciler.py`
- Test: `tests/unit/amm/test_reconciler.py`

**Step 1: Write test** — Redis vs DB drift detection, auto-correction, alerting

**Step 2: Implement** — periodic full-state reconciliation every 5 minutes

**Step 3: Run to verify PASS + Commit**

---

## Task 18: Lifecycle — Graceful Shutdown

**Files:**
- Create: `src/amm/lifecycle/shutdown.py`
- Test: `tests/unit/amm/test_shutdown.py`

**Step 1: Write test** — SIGTERM → batch_cancel all markets → wait for confirms → exit

**Step 2: Implement**

```python
# src/amm/lifecycle/shutdown.py
class GracefulShutdown:
    async def execute(self, contexts: dict[str, MarketContext]) -> None:
        """Cancel all orders across all markets and shutdown cleanly."""
        logger.info("AMM shutdown initiated — cancelling all orders...")
        for market_id, ctx in contexts.items():
            try:
                await self._api.batch_cancel(market_id, scope="ALL")
                logger.info("Cancelled all orders for market %s", market_id)
            except Exception as e:
                logger.error("Failed to cancel orders for %s: %s", market_id, e)

        await self._api.close()
        logger.info("AMM shutdown complete")
```

**Step 3: Run to verify PASS + Commit**

---

## Task 19: Quote Cycle Orchestrator

**Files:**
- Create: `src/amm/main.py`
- Test: `tests/integration/amm/test_amm_quote_cycle.py`

**Step 1: Write integration test**

```python
# tests/integration/amm/test_amm_quote_cycle.py (outline)
class TestQuoteCycle:
    async def test_single_cycle_produces_orders(self) -> None:
        """One quote cycle: sync → strategy → risk → execute."""
        ...

    async def test_cycle_respects_kill_switch(self) -> None:
        """KILL_SWITCH defense level cancels all and stops quoting."""
        ...

    async def test_cycle_handles_api_error_gracefully(self) -> None:
        """API failure in one cycle doesn't crash the loop."""
        ...
```

**Step 2: Implement main loop**

```python
# src/amm/main.py
"""AMM bot entry point."""
import asyncio
import signal
import logging
from src.amm.lifecycle.initializer import AMMInitializer
from src.amm.lifecycle.shutdown import GracefulShutdown
from src.amm.connector.trade_poller import TradePoller
from src.amm.strategy.pricing.three_layer import ThreeLayerPricing
from src.amm.strategy.as_engine import ASEngine
from src.amm.strategy.gradient import GradientEngine
from src.amm.strategy.phase_manager import PhaseManager
from src.amm.risk.defense_stack import DefenseStack
from src.amm.risk.sanitizer import OrderSanitizer
from src.amm.connector.order_manager import OrderManager

logger = logging.getLogger(__name__)


async def quote_cycle(ctx, poller, pricing, as_engine, gradient, risk, sanitizer, order_mgr):
    """Single quote cycle for one market."""
    # Step 1: Sync
    new_trades = await poller.poll(ctx.market_id)

    # Step 2: Strategy (pure computation)
    mid = pricing.compute(
        phase=ctx.phase.value,
        anchor_price=ctx.config.anchor_price_cents,
        best_bid=0,  # TODO: from orderbook snapshot
        best_ask=100,
        recent_trades=[],
    )
    sigma = as_engine.bernoulli_sigma(mid)
    gamma = ctx.config.gamma
    tau = ctx.config.remaining_hours_override or 24.0
    kappa = ctx.config.kappa

    ask, bid = as_engine.compute_quotes(mid, ctx.inventory.inventory_skew, gamma, sigma, tau, kappa)
    ask_ladder = gradient.build_ask_ladder(ask, ctx.config)
    bid_ladder = gradient.build_bid_ladder(bid, ctx.config)

    # Step 3: Risk
    defense = risk.evaluate(
        inventory_skew=ctx.inventory.inventory_skew,
        daily_pnl=ctx.daily_pnl_cents,
        market_active=True,
    )

    if not defense.is_quoting_active:
        await order_mgr.cancel_all(ctx.market_id)
        return

    intents = sanitizer.sanitize(ask_ladder + bid_ladder, defense, ctx)

    # Step 4: Execute
    await order_mgr.execute_intents(intents, ctx.market_id)


async def run_market(ctx, **services):
    """Run quote cycles for a single market."""
    while not ctx.shutdown_requested:
        try:
            await quote_cycle(ctx, **services)
        except Exception as e:
            logger.error("Quote cycle error for %s: %s", ctx.market_id, e)
        await asyncio.sleep(ctx.config.quote_interval_seconds)


async def amm_main():
    """AMM service entry point."""
    # Initialize
    initializer = AMMInitializer(...)
    contexts = await initializer.initialize(market_ids=["mkt-1"])  # from config

    # Register shutdown handler
    shutdown = GracefulShutdown(...)
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown.execute(contexts)))

    # Run quote cycles for all markets concurrently
    tasks = [
        asyncio.create_task(run_market(ctx, ...))
        for ctx in contexts.values()
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(amm_main())
```

**Step 3: Run to verify PASS + Commit**

---

## Task 20: Health Check Endpoint

**Files:**
- Create: `src/amm/lifecycle/health.py`
- Test: `tests/unit/amm/test_health.py`

**Step 1: Implement** — minimal FastAPI app on port 8001 with `/health` and `/readiness`

**Step 2: Run to verify PASS + Commit**

---

## Task 21: Integration Test — Full Startup

**Files:**
- Create: `tests/integration/amm/test_amm_startup.py`

**Step 1: Write test** — verify AMM can start, login, mint, and place initial quotes

**Step 2: Run to verify PASS + Commit**

---

## Task 22: Integration Test — Defense Escalation

**Files:**
- Create: `tests/integration/amm/test_amm_defense_escalation.py`

**Step 1: Write test** — verify defense level progression from NORMAL to KILL_SWITCH

**Step 2: Run to verify PASS + Commit**

---

## Task 23: Integration Test — Graceful Shutdown

**Files:**
- Create: `tests/integration/amm/test_amm_graceful_shutdown.py`

**Step 1: Write test** — send SIGTERM, verify all orders cancelled, clean exit

**Step 2: Run to verify PASS + Commit**

---

## Task 24: Final Verification

**Step 1: Run full AMM test suite**
```bash
uv run pytest tests/unit/amm/ tests/integration/amm/ -v --tb=short
```

**Step 2: Verify no regressions in Phase A tests**
```bash
uv run pytest tests/ -v --tb=short
```

**Step 3: Verify directory structure matches design**
```bash
find src/amm -type f -name "*.py" | sort
# Compare with design doc §3 directory structure
```

**Step 4: Commit final**
```bash
git add -A
git commit -m "feat(amm): Phase B AMM bot implementation complete"
```

---

*Implementation plan ends — 24 Tasks, ~129 test scenarios*
