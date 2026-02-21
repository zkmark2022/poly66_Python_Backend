# 预测市场平台 — 完整实施计划 (Python MVP 版)

> **版本**: v4.1 — Python MVP（单账本撮合引擎架构）
> **目标读者**: 独立开发者，借助 AI Vibe Coding 逐步实现
> **核心变更**: 基于《单账本撮合引擎设计方案 v1》全面重构，单一 YES 订单簿 + 订单转换层 + 四种撮合场景
> **v4 修正**: 在 v3 基础上，从双订单簿架构切换为单账本架构，对齐 exchange-core
> **日期**: 2026-02-20

---

## 零、v4 核心设计原则

以下 6 条原则贯穿整个代码库的每一行代码：

### 原则 1：全局整数化 — 美分制 (Cents-Based Integer Arithmetic)

**规则**: 全系统禁止 `float` 和 `Decimal`，所有价格、金额、数量均使用 `int`（单位：美分）。

**理由**: 预测市场价格被约束在 1–99 美分，YES + NO = 100 美分。这是天然的整数域：
- Python `int` 运算是 C 级原生操作，比 `Decimal` 快 20–50 倍
- 彻底杜绝精度和舍入问题
- 数据库 `BIGINT` 比 `NUMERIC` 更快（索引、比较、存储）
- 成本存储使用 `cost_sum`（累计成本），不使用 `avg_cost`（平均成本），避免整数除法精度丢失

**换算约定**:
```
价格: 1 美分 = 0.01 美元, 范围 [1, 99]
数量: 合约份数, 整数
金额: price_cents * quantity, 单位美分, 整数
显示层: 仅在 API 响应的序列化层将 cents / 100 转换为美元显示
```

### 原则 2：单账本 — 单一 YES 订单簿 + 订单转换层

**规则**: 每个预测话题只维护**一个 YES 订单簿**。所有 NO 操作通过订单转换层映射为 YES 操作后进入同一个订单簿。

**转换规则**:

| 用户操作 | 转换后 | book_type | book_direction | 冻结物 | frozen_asset_type |
|---------|--------|-----------|----------------|--------|-------------------|
| Buy YES @ P | Buy YES @ P | NATIVE_BUY | BUY | 资金 P×qty | FUNDS |
| Sell YES @ P | Sell YES @ P | NATIVE_SELL | SELL | YES 持仓 qty | YES_SHARES |
| Buy NO @ P | Sell YES @ (100-P) | SYNTHETIC_SELL | SELL | 资金 P×qty | FUNDS |
| Sell NO @ P | Buy YES @ (100-P) | SYNTHETIC_BUY | BUY | NO 持仓 qty | NO_SHARES |

**优势**:
- 完全对齐 exchange-core 单账本架构
- 简化撮合逻辑，消除"跨账本"概念
- 流动性集中在一个订单簿，价差更小

### 原则 3：四种撮合场景

根据 Buy 侧和 Sell 侧的订单类型（Native/Synthetic），撮合结果分为四种：

| 场景 | Buy 侧 | Sell 侧 | Reserve 变化 | 业务本质 |
|------|--------|--------|-------------|---------|
| **Mint (铸造)** | NATIVE_BUY | SYNTHETIC_SELL | +100 美分/份 | 创建 YES/NO 合约对 |
| **Transfer YES** | NATIVE_BUY | NATIVE_SELL | 不变 | YES 持仓转手 |
| **Transfer NO** | SYNTHETIC_BUY | SYNTHETIC_SELL | 不变 | NO 持仓转手 |
| **Burn (销毁)** | SYNTHETIC_BUY | NATIVE_SELL | -100 美分/份 | 销毁 YES/NO 合约对 |

**场景判定矩阵**:
```
                    Sell 侧
              ┌────────────┬────────────┐
              │  NATIVE    │ SYNTHETIC  │
              │ (Sell YES) │ (Buy NO)   │
    ┌─────────┼────────────┼────────────┤
Buy │ NATIVE  │ Transfer   │   Mint     │
侧  │(Buy YES)│   YES      │  (铸造)    │
    ├─────────┼────────────┼────────────┤
    │SYNTHETIC│   Burn     │ Transfer   │
    │(Sell NO)│  (销毁)    │    NO      │
    └─────────┴────────────┴────────────┘
```

### 原则 4：请求内同步撮合 — 按市场分片锁 (Per-Market Lock)

**规则**: MVP 阶段在 FastAPI 请求的生命周期内，使用**按 `market_id` 分片的 `asyncio.Lock`** 串行化"转换→风控→撮合→清算→Netting"全链路。

**为什么不用全局锁**: 预测话题之间完全隔离（订单簿独立、Reserve 独立、持仓独立），全局锁会让不同话题的订单被强行串行阻塞，白白浪费吞吐量。分片锁允许不同话题的订单并行处理。

**跨市场余额安全**: 用户余额是跨市场共享的。但无需跨市场加锁——在数据库层使用 `UPDATE accounts SET available_balance = available_balance - X WHERE user_id = Y AND available_balance >= X RETURNING *;` 做原子校验，若余额不足则 RETURNING 空行，业务层据此拒绝订单。

```python
from collections import defaultdict

# 按市场分片的锁字典，懒创建
_market_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

async def place_order(cmd: PlaceOrderCmd):
    market_lock = _market_locks[cmd.market_id]
    async with market_lock:                      # 仅锁定当前话题
        async with db_session.begin():           # 单个数据库事务
            # 1. 订单转换层: NO 操作 → YES 操作
            # 2. 风控检查 + 冻结 (资金或持仓, DB 原子操作)
            # 3. 内存撮合 → Trade 列表 + 场景判定
            # 4. 按场景清算 (Mint/Transfer/Burn)
            # 5. Auto-Netting 净额结算
        # 事务提交后锁才释放
```

### 原则 5：Auto-Netting 净额结算

**规则**: 每次成交后，检查用户是否同时持有同一话题的 YES 和 NO 持仓。若有，自动销毁等量双边持仓并从 Reserve 释放资金。

**调用时机**: 任何可能导致用户持仓增加的操作（Mint 撮合、Transfer 买入）事务内同步调用。

**关键设计决策**:
- 只对"可自由支配"的持仓做 netting，排除 `pending_sell` 冻结的份数
- 全量平仓时跳过除法直接取 `cost_sum` 原值（粉尘防御）
- `pnl_pool` 调整 = 释放资金 - 释放成本，维持 `reserve + pnl_pool == Σ(cost_sum)` 恒等式

```python
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

async def execute_auto_netting(user_id: str, market_id: str, session: AsyncSession) -> int:
    """
    账户层自动净额抵消 (Auto-Netting)

    前置条件: 外部调用方必须已开启数据库事务 (async with session.begin():)
    返回值: 实际抵消的份数 (0 表示无需抵消)
    """

    # 1. 获取并锁定持仓 (FOR UPDATE 悲观写锁)
    stmt_pos = select(PositionModel).where(
        PositionModel.user_id == user_id,
        PositionModel.market_id == market_id
    ).with_for_update()

    position = (await session.execute(stmt_pos)).scalar_one_or_none()
    if not position:
        return 0

    # 2. 计算可抵消的数量 (严格排除正在挂卖单冻结的份数)
    yes_available = position.yes_volume - position.yes_pending_sell
    no_available = position.no_volume - position.no_pending_sell
    nettable_qty = min(yes_available, no_available)

    if nettable_qty <= 0:
        return 0

    logger.info(f"[Auto-Netting] user={user_id}, market={market_id}, qty={nettable_qty}")

    # 3. 计算释放的成本 (核心：粉尘防御机制 Dust Prevention)
    #    全量平仓边界：nettable_qty == yes_volume 只有 pending_sell==0 时才成立
    if nettable_qty == position.yes_volume:
        yes_cost_released = position.yes_cost_sum       # 全量平仓，直接全扣
    else:
        yes_cost_released = (position.yes_cost_sum * nettable_qty) // position.yes_volume

    if nettable_qty == position.no_volume:
        no_cost_released = position.no_cost_sum          # 全量平仓，直接全扣
    else:
        no_cost_released = (position.no_cost_sum * nettable_qty) // position.no_volume

    cost_released_total = yes_cost_released + no_cost_released

    # 4. 执行持仓与历史成本扣减
    position.yes_volume -= nettable_qty
    position.yes_cost_sum -= yes_cost_released
    position.no_volume -= nettable_qty
    position.no_cost_sum -= no_cost_released

    # 防御性断言：cost_sum 不应为负
    assert position.yes_cost_sum >= 0, f"yes_cost_sum went negative: {position.yes_cost_sum}"
    assert position.no_cost_sum >= 0, f"no_cost_sum went negative: {position.no_cost_sum}"

    # 5. 计算释放给用户的金额 (恒定 100 美分/对)
    release_cents = nettable_qty * 100

    # 6. 获取并锁定 Market，更新 Reserve 与 pnl_pool (FOR UPDATE)
    stmt_market = select(MarketModel).where(
        MarketModel.id == market_id
    ).with_for_update()

    market = (await session.execute(stmt_market)).scalar_one()
    market.reserve_balance -= release_cents
    market.total_yes_shares -= nettable_qty
    market.total_no_shares -= nettable_qty

    # 守恒逻辑：释放资金与历史成本的差额沉淀到 pnl_pool
    # 恒等式验证: (R-release) + (P+adjustment) == (C-cost_released)
    #            = R+P-cost_released == C-cost_released  ✓
    pnl_adjustment = release_cents - cost_released_total
    market.pnl_pool += pnl_adjustment

    # 7. 获取并锁定 Account，资金加回可用余额 (FOR UPDATE)
    stmt_account = select(AccountModel).where(
        AccountModel.user_id == user_id
    ).with_for_update()

    account = (await session.execute(stmt_account)).scalar_one()
    account.available_balance += release_cents
    account.version += 1

    # 8. 写入资金流水 (Append-Only)
    ledger_entry = LedgerEntryModel(
        user_id=user_id,
        entry_type="NETTING",
        amount=release_cents,
        balance_after=account.available_balance,
        reference_type="MARKET",
        reference_id=market_id,
        description=f"Auto-netting {nettable_qty} pairs of YES/NO"
    )
    session.add(ledger_entry)

    return nettable_qty
```

### 原则 6：uvloop 高性能事件循环

```python
import uvloop
uvloop.install()  # Python 3.12+ 推荐方式
```

---

## 一、总体阶段划分

| 阶段 | 核心目标 | 预计周期 | 服务形态 | 关键技术 |
|------|----------|----------|----------|----------|
| **Phase 1 — MVP** | 验证核心交易链路：下单→转换→风控→撮合→清算→Netting | 10–14 周 | Python 单体（模块化） | FastAPI, SQLAlchemy, PostgreSQL, Redis, uvloop |
| **Phase 2 — 中期** | 微服务拆分 + 市场管理 + 行情 + 预言机 + 监控 | 10–16 周 | Python 微服务 | Kafka, Consul, TimescaleDB, WebSocket |
| **Phase 3 — 生产就绪** | 高可用、性能关键模块 Java/Rust 重写、合规审计 | 12–20 周 | Python + Java/Rust 混合微服务 | K8s, Flink, Temporal, ClickHouse |

---

## 二、Phase 1 — MVP 详细计划

### 2.1 MVP 包含的功能范围

**包含：**
- 用户账户：注册/登录（JWT）、充值/提现（模拟）、余额查询（所有金额单位：美分）
- 预测话题：静态配置文件定义（暂不需要独立服务）
- 下单：限价单（GTC/IOC），买入/卖出 YES/NO 合约，价格 1–99 美分
- **订单转换层**：将 NO 操作映射为 YES 订单簿操作（单账本核心）
- 风控：余额/持仓检查、单笔限额、持仓限额、自成交预防
- **单账本撮合**：单一 YES 订单簿，O(1) 定长数组，四种撮合场景（Mint/Transfer/Burn）
- **按场景清算**：Mint 进 Reserve、Transfer 用户间转账、Burn 从 Reserve 释放
- Auto-Netting 净额结算 + pnl_pool 追踪
- 查询：订单历史、持仓、账户流水
- Reserve 托管：按话题追踪 reserve_balance / pnl_pool / total_shares
- **平台手续费账户**：累计手续费余额，参与全局零和校验

**不包含（推迟到中期/完备）：**
- 市场生命周期管理（创建、暂停、结算、取消）
- 预言机裁决
- 实时行情推送（K线、深度图）
- 通知系统
- 分布式消息队列（Kafka）
- 服务发现、配置中心
- 监控、链路追踪

### 2.2 MVP 技术栈

| 层次 | 技术选择 | 版本 | 说明 |
|------|----------|------|------|
| 语言 | Python | 3.12+ | 类型提示全覆盖 |
| Web 框架 | FastAPI | 0.109+ | 异步 + 自动 API 文档 |
| ASGI 服务器 | Uvicorn + uvloop | 0.27+ | C 级事件循环 |
| 数据验证 | Pydantic | v2.5+ | Rust 内核 |
| ORM | SQLAlchemy | 2.0+ | 异步模式 (asyncio) |
| 数据库驱动 | asyncpg | 0.29+ | PostgreSQL 异步驱动 |
| 数据库 | PostgreSQL | 16 | 单实例，所有金额字段 BIGINT |
| 缓存 | Redis (redis-py) | 7 / 5.0+ | 会话管理、限流（**不用于余额缓存**） |
| JWT | python-jose | 3.3+ | 或 PyJWT |
| 数据库迁移 | Alembic | 1.13+ | 版本化迁移 |
| 类型检查 | mypy | 1.8+ | 严格模式 |
| 测试 | pytest + pytest-asyncio + httpx | — | 单元 + 集成 + API 测试 |
| 代码质量 | ruff + black | — | Linting + 格式化 |
| 容器 | Docker Compose | — | 本地开发环境 |
| 包管理 | uv 或 Poetry | — | 依赖锁定 |

### 2.3 MVP 代码结构

```
prediction-market/
│
├── pyproject.toml
├── alembic.ini
├── alembic/versions/
│
├── src/
│   ├── pm_common/                    # ===== 模块 0: 公共模块 =====
│   │   ├── __init__.py
│   │   ├── errors.py                 # 统一错误码、自定义异常
│   │   ├── response.py               # ApiResponse[T] 统一响应封装
│   │   ├── id_generator.py           # Snowflake ID 生成器
│   │   ├── cents.py                  # 美分工具: cents_to_display(), validate_price()
│   │   ├── enums.py                  # BookType, OrderStatus 等全局枚举
│   │   ├── datetime_utils.py         # 时间工具
│   │   ├── redis_client.py           # Redis 连接 + Lua 脚本
│   │   └── database.py               # SQLAlchemy async 引擎 + Session
│   │
│   ├── pm_account/                   # ===== 模块 1: 账户模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Account, Position (yes/no 合并行), LedgerEntry
│   │   │   ├── enums.py              # EntryType (含 MINT_COST, BURN_REVENUE 等)
│   │   │   ├── events.py             # BalanceFrozen, PositionUpdated, Netted
│   │   │   ├── service.py            # AccountDomainService
│   │   │   └── repository.py         # Protocol
│   │   ├── infrastructure/
│   │   │   ├── db_models.py          # ORM (BIGINT, positions YES/NO 同行)
│   │   │   ├── persistence.py
│   │   │   └── cache.py              # Redis 查询缓存（余额/冻结纯走 PostgreSQL 事务）
│   │   ├── application/
│   │   │   ├── schemas.py            # Pydantic (cents ↔ display 转换)
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_market/                    # ===== 模块 2: 预测话题配置 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Market (含 reserve_balance, pnl_pool, total_shares)
│   │   │   └── enums.py              # MarketStatus
│   │   ├── config/markets.json
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_order/                     # ===== 模块 3: 订单模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Order (含转换字段: book_type, book_direction, book_price)
│   │   │   ├── enums.py              # BookType, PriceType, OrderStatus, TimeInForce
│   │   │   ├── transformer.py        # ⭐ 订单转换层: NO → YES 映射
│   │   │   ├── events.py
│   │   │   ├── service.py
│   │   │   └── repository.py
│   │   ├── infrastructure/
│   │   │   ├── db_models.py
│   │   │   └── persistence.py
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   ├── commands.py
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_risk/                      # ===== 模块 4: 风控模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # RiskCheckResult
│   │   │   ├── rules.py              # RiskRule Protocol
│   │   │   └── service.py            # RiskDomainService (规则链)
│   │   ├── rules/
│   │   │   ├── balance_check.py      # 按 book_type 分别检查资金或持仓
│   │   │   ├── position_check.py     # Sell 操作: 持仓充足性检查
│   │   │   ├── order_limit.py        # 单笔限额
│   │   │   ├── self_trade.py         # ⭐ 自成交预防
│   │   │   ├── market_status.py
│   │   │   └── price_range.py        # 1 <= price <= 99
│   │   ├── application/service.py
│   │   └── api/router.py
│   │
│   ├── pm_matching/                  # ===== 模块 5: 撮合引擎 ⭐ =====
│   │   ├── domain/
│   │   │   ├── models.py             # MatchResult, Trade (含 scenario)
│   │   │   └── events.py             # TradeExecuted
│   │   ├── engine/
│   │   │   ├── order_book.py         # ⭐ 单一 YES OrderBook: list[deque] O(1)
│   │   │   ├── matching_algo.py      # 价格优先-时间优先 + 场景判定
│   │   │   ├── scenario.py           # ⭐ 场景判定: MINT/TRANSFER_YES/TRANSFER_NO/BURN
│   │   │   ├── market_router.py      # Dict[str, OrderBook] (每话题一个簿)
│   │   │   └── engine.py             # MatchingEngine (同步调用, 无 Queue)
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_clearing/                  # ===== 模块 6: 清算模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Trade, Settlement, Fee (all int cents)
│   │   │   ├── service.py            # ⭐ 按场景分发清算逻辑
│   │   │   ├── scenarios/            # ⭐ 四种场景清算
│   │   │   │   ├── mint.py           # Mint: 双方资金→Reserve, 铸造 YES+NO
│   │   │   │   ├── transfer_yes.py   # Transfer YES: 买方→卖方
│   │   │   │   ├── transfer_no.py    # Transfer NO: 买方→卖方
│   │   │   │   └── burn.py           # Burn: Reserve→双方, 销毁 YES+NO
│   │   │   ├── netting.py            # Auto-Netting (含 pnl_pool 更新)
│   │   │   ├── fee.py                # ⭐ 手续费计算 (Synthetic 用 NO 价格)
│   │   │   └── repository.py
│   │   ├── infrastructure/
│   │   │   ├── db_models.py
│   │   │   └── persistence.py
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_gateway/                   # ===== 模块 7: 网关/认证 =====
│   │   ├── auth/
│   │   │   ├── jwt_handler.py
│   │   │   ├── dependencies.py
│   │   │   └── password.py
│   │   ├── user/
│   │   │   ├── models.py, db_models.py, service.py, schemas.py
│   │   ├── middleware/
│   │   │   ├── rate_limit.py
│   │   │   ├── request_log.py
│   │   │   └── error_handler.py
│   │   └── api/router.py
│   │
│   └── main.py                       # FastAPI 入口 + uvloop.install()
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_order_transformer.py  # ⭐ 订单转换层测试
│   │   ├── test_matching_engine.py    # ⭐ 单账本撮合 16+ 场景
│   │   ├── test_scenario_clearing.py  # ⭐ 四种场景清算测试
│   │   ├── test_auto_netting.py       # ⭐ Netting + pnl_pool 测试
│   │   ├── test_fee_calculation.py    # ⭐ 手续费测试 (Synthetic 用 NO 价格)
│   │   ├── test_self_trade.py         # 自成交预防测试
│   │   ├── test_account_domain.py
│   │   ├── test_order_domain.py
│   │   └── test_risk_rules.py
│   ├── integration/
│   └── e2e/
│       ├── test_full_trading_flow.py  # 含四种场景
│       ├── test_netting_flow.py
│       ├── test_invariant_checks.py   # ⭐ 全部不变量校验
│       └── test_error_scenarios.py
│
├── config/settings.py
├── scripts/
│   └── verify_invariants.py           # 全量不变量校验脚本
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── mypy.ini
```

### 2.4 数据库表设计（单账本版）

```sql
-- 所有金额字段使用 BIGINT, 单位：美分 (cents)

CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) UNIQUE NOT NULL,
    available_balance BIGINT NOT NULL DEFAULT 0,    -- 可用余额 (美分)
    frozen_balance BIGINT NOT NULL DEFAULT 0,       -- 冻结余额 (美分)
    version BIGINT DEFAULT 0,                       -- 乐观锁
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- 含 SYSTEM_RESERVE (全平台托管总池)
-- 含 PLATFORM_FEE (平台手续费账户)

CREATE TABLE markets (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    -- 托管追踪 (单账本核心)
    reserve_balance BIGINT NOT NULL DEFAULT 0,      -- 托管余额 (美分)
    pnl_pool BIGINT NOT NULL DEFAULT 0,             -- 盈亏池 (美分, 可正可负)
    total_yes_shares BIGINT NOT NULL DEFAULT 0,     -- YES 总份数
    total_no_shares BIGINT NOT NULL DEFAULT 0,      -- NO 总份数
    -- 交易规则
    min_price_cents SMALLINT NOT NULL DEFAULT 1,
    max_price_cents SMALLINT NOT NULL DEFAULT 99,
    maker_fee_bps SMALLINT NOT NULL DEFAULT 10,
    taker_fee_bps SMALLINT NOT NULL DEFAULT 20,
    -- ... 其他字段
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ⭐ 持仓表: 每用户每话题一行, YES/NO 合并
CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    -- YES 持仓
    yes_volume INT NOT NULL DEFAULT 0,              -- YES 持有份数
    yes_cost_sum BIGINT NOT NULL DEFAULT 0,         -- YES 累计成本 (美分)
    yes_pending_sell INT NOT NULL DEFAULT 0,        -- YES 卖单冻结份数
    -- NO 持仓
    no_volume INT NOT NULL DEFAULT 0,               -- NO 持有份数
    no_cost_sum BIGINT NOT NULL DEFAULT 0,          -- NO 累计成本 (美分)
    no_pending_sell INT NOT NULL DEFAULT 0,         -- NO 卖单冻结份数
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, market_id)
);

-- ⭐ 订单表: 含单账本转换字段
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id VARCHAR(64) UNIQUE NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    -- 用户原始意图
    original_side VARCHAR(10) NOT NULL,             -- YES / NO (用户选择的合约方向)
    original_direction VARCHAR(10) NOT NULL,        -- BUY / SELL (用户选择的买卖方向)
    original_price SMALLINT NOT NULL,               -- 用户填写的价格 (1-99 美分)
    -- 订单簿视角 (转换后)
    book_type VARCHAR(20) NOT NULL,                 -- NATIVE_BUY / NATIVE_SELL / SYNTHETIC_BUY / SYNTHETIC_SELL
    book_direction VARCHAR(10) NOT NULL,            -- BUY / SELL (订单簿中的方向)
    book_price SMALLINT NOT NULL,                   -- 订单簿中的价格 (1-99 美分)
    -- 定价类型
    price_type VARCHAR(20) NOT NULL DEFAULT 'LIMIT', -- LIMIT (未来可扩展 MARKET)
    time_in_force VARCHAR(10) NOT NULL DEFAULT 'GTC',-- GTC / IOC
    -- 数量
    quantity INT NOT NULL,
    filled_quantity INT DEFAULT 0,
    remaining_quantity INT NOT NULL,
    -- 冻结
    -- ⚠️ 部分成交时必须在清算事务中同步扣减, 否则撤单超额解冻
    frozen_amount BIGINT NOT NULL DEFAULT 0,        -- 当前剩余冻结的资金(美分)或持仓(份数)
    frozen_asset_type VARCHAR(20) NOT NULL,          -- FUNDS / YES_SHARES / NO_SHARES (撤单时据此解冻)
    -- 状态
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    cancel_reason VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ⭐ 成交表: 含撮合场景
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    -- 场景
    scenario VARCHAR(20) NOT NULL,                  -- MINT / TRANSFER_YES / TRANSFER_NO / BURN
    -- 参与方
    buy_order_id UUID NOT NULL,
    sell_order_id UUID NOT NULL,
    buy_user_id VARCHAR(64) NOT NULL,
    sell_user_id VARCHAR(64) NOT NULL,
    buy_book_type VARCHAR(20) NOT NULL,             -- 买方的 book_type
    sell_book_type VARCHAR(20) NOT NULL,            -- 卖方的 book_type
    -- 成交参数 (YES 视角)
    price SMALLINT NOT NULL,                        -- 成交价 (YES 美分, 取 maker 价)
    quantity INT NOT NULL,
    -- Maker/Taker
    maker_order_id UUID NOT NULL,
    taker_order_id UUID NOT NULL,
    -- 手续费
    maker_fee BIGINT NOT NULL DEFAULT 0,
    taker_fee BIGINT NOT NULL DEFAULT 0,
    -- 时间
    executed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    entry_type VARCHAR(30) NOT NULL,                -- 用户侧: DEPOSIT/WITHDRAW/ORDER_FREEZE/ORDER_UNFREEZE/MINT_COST/BURN_REVENUE/TRANSFER_PAYMENT/TRANSFER_RECEIPT/NETTING/FEE
                                                    -- 系统侧: MINT_RESERVE_IN/BURN_RESERVE_OUT/NETTING_RESERVE_OUT/FEE_REVENUE
    amount BIGINT NOT NULL,                         -- 正=入账, 负=出账
    balance_after BIGINT NOT NULL,
    reference_type VARCHAR(30),
    reference_id VARCHAR(64),
    description VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.5 核心交易流程（单账本）

```
用户 A: Buy YES 100份 @65美分 (Native Buy)
用户 B: Buy NO 100份 @38美分 → 转换为 Sell YES @62美分 (Synthetic Sell)

=== 新订单到达 (B 的订单) ===

1. [API] POST /orders {side: NO, direction: BUY, price: 38}
2. [Transform] 订单转换:
     book_type = SYNTHETIC_SELL
     book_direction = SELL
     book_price = 100 - 38 = 62
     original_price = 38
3. [Lock] async with matching_lock:
4.   [Transaction] async with session.begin():
5.     [Risk] 风控检查:
         - B 余额 >= 38 * 100 = 3800 美分? ✅ (冻结 NO 价格, 不是 YES 价格!)
         - 自成交检查: B 在簿中无反向订单? ✅
6.     [Freeze] 冻结 B 的 3800 美分, frozen_amount = 3800, frozen_asset_type = FUNDS
6.1    [Ledger] 写入 ORDER_FREEZE 流水 (entry_type='ORDER_FREEZE', amount=-3800)
7.     [Match] 撮合: A.Buy@65 vs B.Sell@62 → 可成交
         成交价 = 65 (Maker A 的价格)
         场景 = MINT (NATIVE_BUY + SYNTHETIC_SELL)
8.     [Clear] Mint 清算:
         A (Native Buy): 解冻 6500, 扣款 65*100=6500 → Reserve
         B (Synthetic Sell): 解冻 3800, 扣款 (100-65)*100=3500 → Reserve
           退还多冻: 3800 - 3500 = 300 美分
         Reserve: +6500 + 3500 = +10000 美分 ($100)
         A → YES 持仓 +100, yes_cost_sum += 6500
         B → NO 持仓 +100, no_cost_sum += 3500
         market: reserve_balance += 10000, total_yes/no_shares += 100
         手续费: A 按 YES 价 65 计, B 按 NO 价 35 计 (非转换价!)
9.     [Netting] Auto-Netting 检查 A 和 B (本例无需 netting)
10.    [Ledger] 写入流水
11.  [Commit] 事务提交
12. [Unlock] 释放 matching_lock
13. [Response] 返回订单结果
```

---

### 2.6 MVP 模块实现顺序与详细步骤

---

#### 模块 0：项目脚手架与基础设施（第 1 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 0.1 | 初始化 Git 仓库 + 完整目录骨架 | 目录结构, .gitignore |
| 0.2 | 配置 pyproject.toml | pyproject.toml |
| 0.3 | 配置开发工具链 | mypy.ini (strict), ruff.toml |
| 0.4 | Docker Compose | docker-compose.yml (PostgreSQL 16 + Redis 7) |
| 0.5 | SQLAlchemy async 引擎 + Alembic | database.py, alembic.ini |
| 0.6 | 数据库迁移: 全部核心表 (单账本版) | alembic/versions/ |
| 0.7 | Pydantic Settings (.env 驱动) | config/settings.py |
| 0.8 | Makefile | `make dev`, `make test`, `make migrate`, `make lint` |

**验收标准**: `docker-compose up -d && make migrate && make dev` → Swagger 可访问。

---

#### 模块 1：pm_common 公共模块（第 1–2 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.1 | ApiResponse[T] 统一响应 | response.py |
| 1.2 | 错误码 + 自定义异常 | errors.py |
| 1.3 | 全局异常处理 | main.py 中注册 |
| 1.4 | ID 生成器 | id_generator.py |
| 1.5 | 美分工具 + 手续费计算 | cents.py |

```python
# pm_common/cents.py
def calculate_fee(trade_value: int, fee_rate_bps: int) -> int:
    """手续费计算（向上取整，保证平台不亏）"""
    return (trade_value * fee_rate_bps + 9999) // 10000
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.6 | **全局枚举** | enums.py: BookType, TradeScenario 等 |

```python
class BookType(str, Enum):
    NATIVE_BUY = "NATIVE_BUY"           # Buy YES → Buy YES
    NATIVE_SELL = "NATIVE_SELL"          # Sell YES → Sell YES
    SYNTHETIC_BUY = "SYNTHETIC_BUY"      # Sell NO → Buy YES
    SYNTHETIC_SELL = "SYNTHETIC_SELL"     # Buy NO → Sell YES

class TradeScenario(str, Enum):
    MINT = "MINT"                        # 铸造: Native Buy + Synthetic Sell
    TRANSFER_YES = "TRANSFER_YES"        # YES 转手: Native Buy + Native Sell
    TRANSFER_NO = "TRANSFER_NO"          # NO 转手: Synthetic Buy + Synthetic Sell
    BURN = "BURN"                        # 销毁: Synthetic Buy + Native Sell
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.7 | Redis 客户端封装 | redis_client.py |
| 1.8 | 数据库会话管理 | database.py |
| 1.9 | 单元测试 | tests/unit/test_common.py |

---

#### 模块 2：pm_account 账户模块（第 2–3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 2.1 | 领域模型 (全 int) | models.py: Account, Position (YES/NO 合并行), LedgerEntry |

```python
@dataclass
class Position:
    """单账本持仓: 每用户每话题一行, YES/NO 合并"""
    user_id: str
    market_id: str
    yes_volume: int = 0           # YES 持有份数
    yes_cost_sum: int = 0         # YES 累计成本 (美分)
    yes_pending_sell: int = 0     # YES 卖单冻结份数
    no_volume: int = 0            # NO 持有份数
    no_cost_sum: int = 0          # NO 累计成本 (美分)
    no_pending_sell: int = 0      # NO 卖单冻结份数

    @property
    def yes_available(self) -> int:
        return self.yes_volume - self.yes_pending_sell

    @property
    def no_available(self) -> int:
        return self.no_volume - self.no_pending_sell
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 2.2 | 枚举 (含单账本流水类型) | enums.py |
| 2.3 | 仓储接口 + 实现 | repository.py, persistence.py |
| 2.4 | AccountDomainService | service.py: deposit, withdraw, freeze, unfreeze, freeze_position, unfreeze_position |
| 2.5 | ORM 模型 (BIGINT) | db_models.py |
| 2.6 | **PostgreSQL 原子冻结**（`UPDATE ... WHERE available >= X RETURNING *`，**不用 Redis 做余额/冻结**） | persistence.py |
| 2.7 | 应用层 + Pydantic Schemas | application/ |
| 2.8 | REST API | api/router.py |
| 2.9 | 单元测试 | 冻结/解冻、持仓冻结、乐观锁冲突 |
| 2.10 | 集成测试 | DB + Redis + API |

**验收标准**: 充值→冻结资金→冻结持仓→解冻→查流水, 全整数链路跑通。

---

#### 模块 3：pm_market 预测话题配置（第 3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 3.1 | Market 模型 (含 reserve_balance, pnl_pool, total_shares) | domain/models.py |
| 3.2 | 市场状态枚举 | domain/enums.py |
| 3.3 | 静态配置 JSON | config/markets.json |
| 3.4 | MarketConfigService | application/service.py |
| 3.5 | REST API | api/router.py |
| 3.6 | 测试 | tests/ |

**验收标准**: GET /markets 返回话题列表, 含 reserve_balance / pnl_pool / total_shares 字段。

---

#### 模块 4：pm_order 订单模块（第 3–4 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.1 | 枚举 | BookType, PriceType, OrderStatus, TimeInForce |
| 4.2 | Order 领域模型 (含转换字段) | domain/models.py |

```python
@dataclass
class Order:
    id: str
    client_order_id: str
    market_id: str
    user_id: str
    # 用户原始意图
    original_side: str              # YES / NO
    original_direction: str         # BUY / SELL
    original_price: int             # 1-99 美分
    # 订单簿视角 (转换后)
    book_type: str                  # NATIVE_BUY / NATIVE_SELL / SYNTHETIC_BUY / SYNTHETIC_SELL
    book_direction: str             # BUY / SELL
    book_price: int                 # 1-99 美分
    # 定价
    price_type: str = "LIMIT"
    time_in_force: str = "GTC"
    # 数量
    quantity: int = 0
    filled_quantity: int = 0
    remaining_quantity: int = 0
    # 冻结
    frozen_amount: int = 0          # 冻结的资金(美分)或持仓(份数)
    frozen_asset_type: str = ""     # FUNDS / YES_SHARES / NO_SHARES
    status: str = "NEW"
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.3 | **⭐ 订单转换层** | domain/transformer.py |

```python
def transform_order(side: str, direction: str, price: int) -> tuple[str, str, int]:
    """
    将用户意图转换为订单簿操作
    Returns: (book_type, book_direction, book_price)
    """
    if side == "YES":
        if direction == "BUY":
            return ("NATIVE_BUY", "BUY", price)
        else:
            return ("NATIVE_SELL", "SELL", price)
    else:  # NO
        if direction == "BUY":
            return ("SYNTHETIC_SELL", "SELL", 100 - price)
        else:
            return ("SYNTHETIC_BUY", "BUY", 100 - price)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.4 | 状态机 | 内嵌在 Order 模型中 |
| 4.5 | 仓储接口 + 实现 | repository.py + infrastructure/ |
| 4.6 | 应用层 | application/ |
| 4.7 | REST API | POST /orders, DELETE /orders/{id}, GET /orders |
| 4.8 | **订单转换层测试** | tests/unit/test_order_transformer.py |
| 4.9 | 单元测试 | 状态机, 幂等, 转换正确性 |

**转换层测试场景**:

| # | 输入 | 期望 book_type | 期望 book_price |
|---|------|---------------|----------------|
| 1 | Buy YES @65 | NATIVE_BUY | 65 |
| 2 | Sell YES @67 | NATIVE_SELL | 67 |
| 3 | Buy NO @35 | SYNTHETIC_SELL | 65 |
| 4 | Sell NO @40 | SYNTHETIC_BUY | 60 |
| 5 | Buy NO @1 | SYNTHETIC_SELL | 99 |
| 6 | Buy NO @99 | SYNTHETIC_SELL | 1 |

---

#### 模块 5：pm_risk 风控模块（第 4–5 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 5.1 | RiskRule Protocol | domain/rules.py |
| 5.2 | **balance_check.py (按 book_type 分别检查)** | rules/ |

```python
def check_and_freeze(order: Order, account: Account, position: Position) -> bool:
    """按订单类型检查并冻结对应资产，同时设置 frozen_asset_type"""
    if order.book_type == "NATIVE_BUY":
        # 冻结资金: original_price × quantity
        amount = order.original_price * order.quantity
        order.frozen_amount = amount
        order.frozen_asset_type = "FUNDS"
        return freeze_balance(account, amount)  # DB: UPDATE ... WHERE available >= X

    elif order.book_type == "NATIVE_SELL":
        # 冻结 YES 持仓: quantity
        order.frozen_amount = order.quantity
        order.frozen_asset_type = "YES_SHARES"
        return freeze_yes_position(position, order.quantity)

    elif order.book_type == "SYNTHETIC_SELL":
        # Buy NO → 冻结资金: original_price × quantity (NO 价格!)
        amount = order.original_price * order.quantity
        order.frozen_amount = amount
        order.frozen_asset_type = "FUNDS"
        return freeze_balance(account, amount)  # DB: UPDATE ... WHERE available >= X

    elif order.book_type == "SYNTHETIC_BUY":
        # Sell NO → 冻结 NO 持仓: quantity
        order.frozen_amount = order.quantity
        order.frozen_asset_type = "NO_SHARES"
        return freeze_no_position(position, order.quantity)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 5.3 | **self_trade.py (自成交预防)** | rules/ |
| 5.4 | order_limit.py, market_status.py, price_range.py | rules/ |
| 5.5 | RiskDomainService (规则链) | domain/service.py |
| 5.6 | 单元测试 | 每条规则 pass/reject, 自成交检测 |

---

#### 模块 6：pm_matching 撮合引擎（第 5–7 周）⭐ 核心难点

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.1 | **⭐ 单一 YES 订单簿** | engine/order_book.py |

```python
@dataclass
class OrderBook:
    """单一 YES 订单簿 — 每个预测话题只有一个"""
    market_id: str

    # index 0 废弃; index 1-99 对应 YES 价格 1-99 美分
    bids: list[deque] = field(default_factory=lambda: [deque() for _ in range(100)])
    asks: list[deque] = field(default_factory=lambda: [deque() for _ in range(100)])

    best_bid: int = 0    # 最高买价 (YES), 0 = 无买单
    best_ask: int = 100  # 最低卖价 (YES), 100 = 无卖单
```

注意：不再有 `contract_type` 参数，因为只有一个 YES 簿。Native 和 Synthetic 订单混合在同一个簿中。

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.2 | **⭐ 场景判定** | engine/scenario.py |

```python
def determine_scenario(buy_order: Order, sell_order: Order) -> TradeScenario:
    """根据 buy/sell 的 book_type 判定撮合场景"""
    buy_is_native = buy_order.book_type in ("NATIVE_BUY",)
    sell_is_native = sell_order.book_type in ("NATIVE_SELL",)

    if buy_is_native and not sell_is_native:
        return TradeScenario.MINT
    elif buy_is_native and sell_is_native:
        return TradeScenario.TRANSFER_YES
    elif not buy_is_native and not sell_is_native:
        return TradeScenario.TRANSFER_NO
    else:  # not buy_is_native and sell_is_native
        return TradeScenario.BURN
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.3 | 撮合算法 (价格优先-时间优先) | engine/matching_algo.py |
| 6.4 | 市场路由 | engine/market_router.py: Dict[str, OrderBook] (每话题一个!) |
| 6.5 | MatchingEngine | engine/engine.py |
| 6.6 | 应用层 + API | application/, api/ |
| 6.7 | **⭐ 单元测试 (16+ 场景)** | tests/unit/test_matching_engine.py |

**撮合测试场景**:

| # | 场景 | Buy 侧 | Sell 侧 | 预期场景 | 预期成交价 |
|---|------|--------|--------|---------|-----------|
| 1 | Mint 基本 | Buy YES @65 | Buy NO @38 (→Sell@62) | MINT | 65 (maker价) |
| 2 | Transfer YES | Buy YES @65 | Sell YES @60 | TRANSFER_YES | 60 (maker价) |
| 3 | Transfer NO | Sell NO @40 (→Buy@60) | Buy NO @42 (→Sell@58) | TRANSFER_NO | 60 (maker价) |
| 4 | Burn | Sell NO @35 (→Buy@65) | Sell YES @60 | BURN | 60 (maker价) |
| 5 | Mint 价格优化 | Buy YES @65 (maker) | Buy NO @38 (→Sell@62) | MINT | 65, 溢价归 maker |
| 6 | 部分成交 | Buy YES 200@65 | Buy NO 100@35 (→Sell@65) | MINT | 成交100, 剩余100挂单 |
| 7 | IOC 取消剩余 | IOC Buy YES 200@65 | Sell YES 50@60 | TRANSFER_YES | 成交50, 取消150 |
| 8 | 不交叉 | Buy YES @50 | Sell YES @60 | - | 不成交, 双方挂单 |
| 9 | 时间优先 | 同价多笔 | - | - | 先到先成交 |
| 10 | 边界 BUY@99 | Buy YES @99 | Buy NO @1 (→Sell@99) | MINT | 99 |
| 11 | 自成交阻止 | 用户A Buy@65 | 用户A Sell@60 | - | 拒绝, SELF_TRADE |
| 12 | 多笔连续 | Buy 200@65 | [Sell 50@55, Sell 80@60, Sell 100@65] | 混合场景 | 3笔成交 |
| 13 | Native+Synthetic 混合簿 | Buy YES@65 + Sell NO@33(→Buy@67) | Sell YES@60 | maker 是 Sell@60 | 先与 Sell NO 的 Buy@67 成交 |
| 14 | Burn 释放 Reserve | Sell NO@35(→Buy@65) | Sell YES@65 | BURN | Reserve -100 |
| 15 | 空簿挂单 | Buy YES@60 | - | - | 挂入 bids[60] |
| 16 | 取消挂单 | - | - | - | 从 deque 移除 |

---

#### 模块 7：pm_clearing 清算模块（第 7–9 周）⭐

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.1 | **⭐ 手续费计算 (区分 Native/Synthetic)** | domain/fee.py |

```python
def get_fee_trade_value(order: Order, trade_price: int, qty: int) -> int:
    """根据 book_type 获取手续费计算基础"""
    if order.book_type in ("NATIVE_BUY", "NATIVE_SELL"):
        return trade_price * qty                    # YES 价格
    elif order.book_type == "SYNTHETIC_SELL":
        return order.original_price * qty           # NO 价格 (用户实际支付)
    elif order.book_type == "SYNTHETIC_BUY":
        return (100 - trade_price) * qty            # NO 价格
    raise ValueError(f"Unknown book_type: {order.book_type}")
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.2 | **⭐ 四种场景清算** | domain/scenarios/ |

```python
# scenarios/mint.py
async def clear_mint(trade: Trade, market: Market, session: AsyncSession):
    """Mint: Native Buy + Synthetic Sell → 创建合约对"""
    buyer = trade.buy_user_id
    seller = trade.sell_user_id
    price = trade.price           # YES 成交价
    qty = trade.quantity

    # 买方: 解冻 → 扣款 → 获得 YES
    buyer_cost = price * qty
    await unfreeze_and_debit(buyer, trade.buy_order.frozen_amount, buyer_cost, session)
    await add_yes_volume(buyer, trade.market_id, qty, buyer_cost, session)

    # 卖方 (Buy NO): 解冻 → 扣款 → 获得 NO
    seller_cost = (100 - price) * qty
    await unfreeze_and_debit(seller, trade.sell_order.frozen_amount, seller_cost, session)
    await add_no_volume(seller, trade.market_id, qty, seller_cost, session)

    # Reserve: +100 美分/份
    market.reserve_balance += qty * 100
    market.total_yes_shares += qty
    market.total_no_shares += qty

# scenarios/transfer_yes.py
async def clear_transfer_yes(trade: Trade, market: Market, session: AsyncSession):
    """Transfer YES: Native Buy + Native Sell → YES 转手"""
    price = trade.price
    qty = trade.quantity

    # 买方: 解冻 → 扣款 → 获得 YES
    buyer_cost = price * qty
    await unfreeze_and_debit(trade.buy_user_id, ..., buyer_cost, session)
    await add_yes_volume(trade.buy_user_id, trade.market_id, qty, buyer_cost, session)

    # 卖方: 释放持仓冻结 → 扣减 YES → 收入
    seller_revenue = price * qty
    seller_cost_released = proportional_cost(position, qty)  # 按比例释放 cost_sum
    await reduce_yes_volume(trade.sell_user_id, trade.market_id, qty, session)
    await credit(trade.sell_user_id, seller_revenue, session)

    # pnl_pool: 追踪 Transfer 盈亏
    seller_pnl = seller_revenue - seller_cost_released
    market.pnl_pool -= seller_pnl

# scenarios/burn.py → Reserve -100/份, 销毁 YES+NO
# scenarios/transfer_no.py → NO 转手, 类似 transfer_yes
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.3 | **清算分发器** | domain/service.py |

```python
async def settle_trade(trade: Trade, market: Market, session: AsyncSession):
    """按场景分发清算"""
    if trade.scenario == "MINT":
        await clear_mint(trade, market, session)
    elif trade.scenario == "TRANSFER_YES":
        await clear_transfer_yes(trade, market, session)
    elif trade.scenario == "TRANSFER_NO":
        await clear_transfer_no(trade, market, session)
    elif trade.scenario == "BURN":
        await clear_burn(trade, market, session)

    # 扣手续费
    await collect_fees(trade, session)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.4 | **⭐ Auto-Netting (含 pnl_pool 更新)** | domain/netting.py |
| 7.5 | 应用层 + API | application/, api/ |
| 7.6 | **四种场景清算测试** | tests/unit/test_scenario_clearing.py |
| 7.7 | **手续费测试** | tests/unit/test_fee_calculation.py |
| 7.8 | **Netting + pnl_pool 测试** | tests/unit/test_auto_netting.py |
| 7.9 | 集成测试 | 撮合→清算→netting→余额+持仓+流水 |

**验收标准**: 四种场景清算正确; Reserve 不变量成立; pnl_pool 追踪正确; 手续费 Synthetic 用 NO 价格。

---

#### 模块 8：pm_gateway 网关/认证（第 9–10 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 8.1 | User 模型 + ORM | user/ |
| 8.2 | bcrypt 密码哈希 | auth/password.py |
| 8.3 | JWT 生成/验证 | auth/jwt_handler.py |
| 8.4 | FastAPI Depends(get_current_user) | auth/dependencies.py |
| 8.5 | 注册/登录 API | api/router.py |
| 8.6 | 限流中间件 | middleware/rate_limit.py |
| 8.7 | 请求日志 + 全局异常处理 | middleware/ |
| 8.8 | 所有业务 Router 加认证 | Depends(get_current_user) |
| 8.9 | 测试 | JWT, 密码哈希, 鉴权拦截 |

---

#### 模块 9：端到端集成（第 10–12 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.1 | main.py 串联所有模块 + uvloop | main.py |
| 9.2 | **核心交易入口 (单账本版)** | 整合 matching_lock 流程 |

```python
async def place_order_flow(cmd: PlaceOrderCmd, user: User, session: AsyncSession):
    # 0. 订单转换
    book_type, book_direction, book_price = transform_order(
        cmd.side, cmd.direction, cmd.price
    )
    order = Order.create(cmd, book_type, book_direction, book_price)

    market_lock = _market_locks[cmd.market_id]
    async with market_lock:                          # 按市场分片锁
        async with session.begin():
            # 1. 风控检查 + 冻结 (按 book_type 冻结资金或持仓, DB 原子操作)
            risk_result = await risk_service.check_and_freeze(order, session)
            if not risk_result.passed:
                return OrderResult.rejected(risk_result)

            # 1.1 写入 ORDER_FREEZE 流水 (挂单时资金去向可追溯)
            await ledger_service.record_freeze(order, session)

            # 2. 自成交检查
            if await self_trade_check(order, session):
                return OrderResult.rejected("SELF_TRADE_PREVENTED")

            # 3. 同步撮合 (单一 YES 订单簿)
            trades = matching_engine.submit_order(order)

            # 4. 持久化订单
            await order_repo.save(order, session)

            # 5. 逐笔按场景清算
            market = await market_repo.get(order.market_id, session)
            for trade in trades:
                trade.scenario = determine_scenario(trade.buy_order, trade.sell_order)
                await clearing_service.settle_trade(trade, market, session)

                # 6. Auto-Netting (两个参与方都检查)
                await netting_service.auto_netting(trade.buy_user_id, trade.market_id, session)
                await netting_service.auto_netting(trade.sell_user_id, trade.market_id, session)

            # 7. 持久化成交 + 更新 market
            await trade_repo.save_all(trades, session)
            await market_repo.save(market, session)

    return OrderResult.accepted(order, trades)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.3 | **⭐ 不变量校验脚本** | scripts/verify_invariants.py |

```python
async def verify_all_invariants(session: AsyncSession):
    """全量不变量校验（对齐单账本设计方案第九章）"""
    for market in await get_all_active_markets(session):
        # 不变量 1: 份数平衡
        assert market.total_yes_shares == market.total_no_shares

        # 不变量 2: 托管平衡
        assert market.reserve_balance == market.total_yes_shares * 100

        # 不变量 3: 成本守恒
        total_cost_sum = await sum_all_cost_sums(market.id, session)
        assert market.reserve_balance + market.pnl_pool == total_cost_sum

    # 全局零和 (含手续费)
    total_user = await sum_all_user_balances(session)         # available + frozen
    total_reserve = await sum_all_market_reserves(session)    # Σ reserve_balance
    total_fees = await get_platform_fee_balance(session)
    net_deposits = await sum_deposits(session) - await sum_withdrawals(session)
    assert total_user + total_reserve + total_fees == net_deposits
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.4 | E2E 完整流程测试 (含四种场景) | tests/e2e/test_full_trading_flow.py |
| 9.5 | Netting E2E 测试 | tests/e2e/test_netting_flow.py |
| 9.6 | 不变量 E2E 测试 | tests/e2e/test_invariant_checks.py |
| 9.7 | 异常场景测试 | tests/e2e/test_error_scenarios.py |
| 9.8 | Dockerfile + docker-compose | Dockerfile, docker-compose.yml |
| 9.9 | Seed 数据脚本 | scripts/seed_data.py |

**E2E 完整流程 (单账本)**:
```
1. 注册用户 A, B, C
2. A, B, C 各充值 100_000 美分 ($1000)
3. A: Buy YES 100@65 → 挂单 (NATIVE_BUY, 冻结 6500)
4. B: Buy NO 100@35 → 转换为 Sell YES@65 → 与 A 撮合
   场景: MINT, 成交价 65
   验证: Reserve +10000, A 获 100 YES, B 获 100 NO
5. C: Buy YES 50@70 → A 无卖单 → 挂单
6. A: Sell YES 50@68 → 与 C@70 撮合
   场景: TRANSFER_YES, 成交价 68 (maker A 的价)
   验证: A 减 50 YES 获 3400 美分, C 加 50 YES
7. B: Sell NO 30@40 → 转换为 Buy YES@60 → 需要有 Sell YES 挂单
   ... 构造 BURN 场景
8. 不变量校验:
   - total_yes_shares == total_no_shares ✓
   - reserve_balance == shares * 100 ✓
   - reserve + pnl_pool == Σ(cost_sum) ✓
   - Σ(user balance) + Σ(reserve) + fees == Σ(deposits) ✓
```

**验收标准**: `docker-compose up` → `pytest tests/ -v` 全绿 → 全部不变量校验通过。

---

### 2.7 MVP 里程碑

```
Week 1:    [脚手架 + pm_common] ─── Docker, DB(单账本表结构), 枚举, uvloop
Week 2-3:  [pm_account] ────────── 充值/冻结/持仓(YES/NO 合并行) + cost_sum
Week 3:    [pm_market] ─────────── 话题配置 (含 reserve/pnl_pool/shares)
Week 4:    [pm_order] ──────────── 订单 + ⭐转换层 (NO→YES 映射)
Week 5:    [pm_risk] ───────────── 风控 (按 book_type 冻结) + 自成交预防
Week 6-7:  [pm_matching] ──────── ⭐单一 YES 订单簿 + 四种场景判定
Week 8-9:  [pm_clearing] ────────── ⭐四种场景清算 + pnl_pool + Netting
Week 10:   [pm_gateway] ─────────── JWT 认证 + 限流
Week 11-12:[E2E + 发布] ─────────── matching_lock 集成 + 不变量校验 🎉
```

---

## 三、Phase 2 — 中期实施计划

### 3.1 核心目标
微服务拆分 + 市场结算/取消 + 行情 + 预言机 + 监控。

### 3.2 实施顺序

| 优先级 | 模块 | 关键变更 | 预计周期 |
|--------|------|----------|----------|
| **P0** | 基础设施升级 | Kafka (Redpanda) + Consul | 2 周 |
| **P0** | 微服务拆分 | 每个 pm_* → 独立 FastAPI | 3 周 |
| **P1** | pm-market-service | 市场生命周期 + 结算 + 取消 (基于 pnl_pool 精确退款) | 2 周 |
| **P1** | pm-oracle-service | 数据采集 + 人工裁决 + 结算触发 | 2 周 |
| **P2** | pm-market-data-service | TimescaleDB K线 + WebSocket 推送 | 2 周 |
| **P2** | pm-notification-service | Kafka 消费 + 通知 | 2 周 |
| **P3** | API Gateway | 替换内嵌路由 | 1 周 |
| **P3** | 监控 | Prometheus + Grafana + Jaeger | 2 周 |

---

## 四、Phase 3 — 生产就绪计划

| 优先级 | 模块 | 关键升级 |
|--------|------|----------|
| **P0** | 撮合引擎重写 | Java + LMAX Disruptor 或 Rust |
| **P0** | 数据库高可用 | PostgreSQL 主从 + 连接池 |
| **P0** | K8s 部署 | 多副本 + 自动故障转移 |
| **P1** | 市场结算完善 | 争议期、多源验证 |
| **P1** | 智能风控 | 规则引擎 + 反操纵检测 |
| **P2** | 分析系统 | ClickHouse + 对账 + 反作弊 |
| **P2** | 审计合规 | 不可篡改日志 |

---

## 附录 A：v4.0 → v4.1 修正对照表

| v4.0 设计 | v4.1 修正 | 理由 |
|-----------|----------|------|
| 全局 `asyncio.Lock` | 按 `market_id` 分片锁 `dict[str, asyncio.Lock]` | 话题间完全隔离，全局锁白白浪费吞吐量 |
| Redis Lua 原子冻结余额 | 纯 PostgreSQL 事务内 `UPDATE ... WHERE available >= X RETURNING *` | 避免 Redis↔PG 双写一致性灾难，事务回滚时 Redis 永久冻结 |
| Auto-Netting `//` 无边界判断 | 全量平仓时直接取 `cost_sum` 原值 | 防止整数除法粉尘残留破坏恒等式 |
| `frozen_amount` 无类型标识 | 增加 `frozen_asset_type` 枚举 (FUNDS/YES_SHARES/NO_SHARES) | 撤单时明确解冻资产类型，防止资金↔持仓混淆 |
| 挂单无流水记录 | 冻结时写 ORDER_FREEZE 流水，撤单时写 ORDER_UNFREEZE 流水 | 用户对账单可追溯资金去向 |

---

## 附录 B：v3 → v4 修正对照表

| v3 设计 | v4 (单账本) | 理由 |
|---------|------------|------|
| YES/NO 双订单簿 | 单一 YES 订单簿 + 转换层 | 对齐 exchange-core，流动性集中 |
| 无订单转换 | 订单转换层 (NO→YES 映射) | 单账本核心组件 |
| 仅 BUY/SELL 撮合 | 四种场景: MINT/TRANSFER/BURN | 单账本撮合产生四种结果 |
| `avg_entry_price` | `cost_sum` (累计成本) | 避免整数除法精度丢失 |
| positions: (user, market, contract_type) 一行 | positions: (user, market) 一行, YES/NO 合并 | 对齐 exchange-core PositionRecord |
| 无 `pending_sell` | `yes_pending_sell` + `no_pending_sell` | 卖单需冻结持仓 |
| 无 `frozen_amount` 在 orders | `frozen_amount` 字段 | 取消时精确解冻 |
| 无 `pnl_pool` | `pnl_pool` 在 markets 表 | Transfer 盈亏追踪，成本守恒 |
| `total_matched_pairs` + `escrowed_cents` | `reserve_balance` + `total_yes/no_shares` | 对齐单账本设计方案 |
| 无 `scenario` 在 trades | `scenario` 字段 | 清算按场景分发 |
| 无 `book_type` / `book_direction` | 订单含完整转换字段 | 持久化订单簿身份 |
| `order_type` = LIMIT | `price_type` = LIMIT | 避免与 book_type 混淆 |
| 手续费统一计费基础 | Synthetic 订单用 NO 价格 | 防止深虚值 NO 费率爆炸 |
| 零和 = users + reserve | 零和 = users + reserve + fees | 手续费也是系统资金 |
| Phase 3 才做"合成撮合" | MVP 即实现 (单账本天然支持) | 不再是未来功能 |
| 无自成交预防 | Self-Trade Prevention | 防止用户误操作 |

---

*文档版本: v4.1 (单账本撮合引擎架构) | 生成日期: 2026-02-20*
