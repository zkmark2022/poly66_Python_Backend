# 预测市场平台 — 完整实施计划 (Python MVP 版)

> **版本**: v3.0 — Python MVP（整合二元市场核心设计修正）
> **目标读者**: 独立开发者，借助 AI Vibe Coding 逐步实现
> **核心变更**: MVP 全部使用 Python，保持模块化设计，支持将来逐模块替换为 Java/Rust
> **v3 修正**: 全局整数化(美分制)、O(1)定长数组订单簿、请求内同步撮合、Auto-Netting净额结算、uvloop
> **日期**: 2026-02-20

---

## 零、v3 核心设计原则（二元预测市场专用）

在深入模块计划之前，以下 5 条原则贯穿整个代码库的每一行代码：

### 原则 1：全局整数化 — 美分制 (Cents-Based Integer Arithmetic)

**规则**: 全系统禁止 `float` 和 `Decimal`，所有价格、金额、数量均使用 `int`（单位：美分）。

**理由**: 预测市场价格被约束在 1–99 美分，YES + NO = 100 美分。这是天然的整数域：
- Python `int` 运算是 C 级原生操作，比 `Decimal` 快 20–50 倍
- 彻底杜绝精度和舍入问题
- 数据库 `BIGINT` 比 `NUMERIC` 更快（索引、比较、存储）

**换算约定**:
```
价格: 1 美分 = 0.01 美元, 范围 [1, 99]
数量: 合约份数, 整数
金额: price_cents * quantity, 单位美分, 整数
显示层: 仅在 API 响应的序列化层将 cents / 100 转换为美元显示
```

**示例**:
```python
# ✅ 正确
order_cost: int = price_cents * quantity  # 60 * 100 = 6000 cents = $60.00
fee: int = order_cost * 2 // 10000       # 0.02% fee, 整数除法

# ❌ 禁止
from decimal import Decimal  # 不要在任何业务逻辑中使用
price: float = 0.60          # 绝对禁止
```

### 原则 2：O(1) 定长数组订单簿

**规则**: 订单簿使用 `list[deque[Order]]` 长度 100 的定长数组，价格直接作为 index。

**理由**: 价格空间 [1, 99] 是有限离散整数集，数组索引寻址 O(1) 碾压任何树形结构 O(log N)。

```python
class OrderBook:
    def __init__(self, market_id: str):
        self.market_id = market_id
        # index 0 废弃，index 1-99 对应价格 1-99 美分
        self.bids: list[deque[Order]] = [deque() for _ in range(100)]
        self.asks: list[deque[Order]] = [deque() for _ in range(100)]
        self.best_bid: int = 0   # 缓存最优买价 (无买单时为 0)
        self.best_ask: int = 100 # 缓存最优卖价 (无卖单时为 100)
```

### 原则 3：请求内同步撮合 — 无 Queue 解耦

**规则**: MVP 阶段废弃 `asyncio.Queue`。在 FastAPI 请求的生命周期内，使用 `asyncio.Lock` 串行化"风控→撮合→清算"全链路。

**理由**: `AsyncSession` 绑定在当前协程上下文，跨协程传递事务会导致死锁或数据撕裂。单体 MVP 必须在一个请求中完成完整的事务闭环。

```python
matching_lock = asyncio.Lock()  # 全局锁，保证单线程撮合

async def place_order(cmd: PlaceOrderCmd):
    async with matching_lock:                    # 串行化整个关键路径
        async with db_session.begin():           # 单个数据库事务
            # 1. 查库验证 + 风控检查 + 余额冻结
            # 2. 内存撮合 → Trade 列表
            # 3. 清算写库 (trades, ledger, account, position)
            # 4. Auto-Netting 净额结算
        # 事务提交后锁才释放
    # 返回 HTTP 响应
```

**锁的范围覆盖整个事务**，确保内存订单簿与数据库状态严格一致。

### 原则 4：Auto-Netting 净额结算

**规则**: 每次成交后，检查用户是否同时持有同一市场的 YES 和 NO 头寸。若有，自动销毁等量双边头寸并释放资金。

**理由**: 用户持有 100 YES + 100 NO = 无论结果都得 $100。不做 netting 会导致资金被无意义锁定，Reserve 账本差错。

```python
async def auto_netting(user_id: str, market_id: str, session: AsyncSession):
    yes_pos = await get_position(user_id, market_id, "YES", session)
    no_pos = await get_position(user_id, market_id, "NO", session)
    nettable = min(yes_pos.quantity, no_pos.quantity)
    if nettable > 0:
        # 销毁双边等量持仓
        yes_pos.quantity -= nettable
        no_pos.quantity -= nettable
        # 从 Reserve 释放资金: nettable * 100 cents
        release_amount = nettable * 100  # 每对 YES+NO = $1.00
        await credit_user_balance(user_id, release_amount, session)
        await debit_reserve(release_amount, session)
        # 记录流水
        await write_ledger_entry(user_id, "NETTING", release_amount, session)
```

### 原则 5：uvloop 高性能事件循环

**规则**: 强制使用 uvloop 替代标准 asyncio 事件循环。

```python
# main.py
import uvloop
uvloop.install()  # Python 3.12+ 推荐方式

# 或通过 uvicorn 启动参数: uvicorn main:app --loop uvloop
```

---

## 一、总体阶段划分

| 阶段 | 核心目标 | 预计周期 | 服务形态 | 关键技术 |
|------|----------|----------|----------|----------|
| **Phase 1 — MVP** | 验证核心交易链路：下单→风控→撮合→清算→记账 | 8–12 周 | Python 单体（模块化） | FastAPI, SQLAlchemy, PostgreSQL, Redis, uvloop |
| **Phase 2 — 中期** | 微服务拆分 + 市场管理 + 行情 + 预言机 + 监控 | 10–16 周 | Python 微服务（核心链路可选 Java 重写） | Kafka, Consul, TimescaleDB, WebSocket |
| **Phase 3 — 生产就绪** | 高可用、性能关键模块 Java/Rust 重写、合规审计 | 12–20 周 | Python + Java/Rust 混合微服务 | K8s, Flink, Temporal, ClickHouse |

### 为什么 Python MVP 是合理的？

**优势：**
- 开发速度快，FastAPI 自带 Swagger 文档，极大缩短 API 开发周期
- Python 生态丰富，AI 代码生成对 Python 的支持最好
- 所有模块统一语言，降低心智负担
- Pydantic v2 (Rust 内核) 验证性能优秀
- 整数化设计 + 定长数组订单簿，大幅降低 Python 性能劣势
- 对于 MVP 级别的并发（数百~数千 TPS），Python 完全胜任

**将来替换策略：**
```
Phase 1 (全 Python)     →  Phase 2 (拆分微服务)     →  Phase 3 (性能关键模块替换)
                              │                              │
pm_matching (Python)     →  pm-matching-service      →  Java/Rust 重写
pm_clearing (Python)     →  pm-clearing-service      →  Java 重写（可选）
pm_account (Python)      →  pm-account-service       →  保持 Python 或 Java
pm_risk (Python)         →  pm-risk-service          →  保持 Python 或 Java
```

---

## 二、Phase 1 — MVP 详细计划

### 2.1 MVP 包含的功能范围

**包含：**
- 用户账户：注册/登录（JWT）、充值/提现（模拟）、余额查询（所有金额单位：美分）
- 市场：静态配置文件定义市场（暂不需要独立服务）
- 下单：限价单（GTC/IOC），买入 YES/NO 合约，价格 1–99 美分
- 风控：余额检查、单笔限额、持仓限额（硬编码规则）
- 撮合：单线程限价订单簿（LOB），O(1) 定长数组，YES/NO 独立撮合
- 清算：成交后资金划转、手续费扣除、持仓更新、**Auto-Netting 净额结算**
- 查询：订单历史、持仓、账户流水
- Reserve 账户：系统托管池，所有交易资金的对手方

**不包含（推迟到中期/完备）：**
- 市场生命周期管理（创建、暂停、结算）
- 预言机裁决
- 实时行情推送（K线、深度图）
- 通知系统
- 合成撮合（YES+NO 对冲下单）
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
| 数据库 | PostgreSQL | 16 | 单实例，**所有金额字段 BIGINT** |
| 缓存 | Redis (redis-py) | 7 / 5.0+ | 余额缓存、分布式锁 |
| JWT | python-jose | 3.3+ | 或 PyJWT |
| 数据库迁移 | Alembic | 1.13+ | 版本化迁移 |
| 类型检查 | mypy | 1.8+ | 严格模式 |
| 测试 | pytest + pytest-asyncio + httpx | — | 单元 + 集成 + API 测试 |
| 代码质量 | ruff + black | — | Linting + 格式化 |
| 容器 | Docker Compose | — | 本地开发环境 |
| 包管理 | uv 或 Poetry | — | 依赖锁定 |

**注意：无需安装 `sortedcontainers`**，订单簿使用原生 `list` + `collections.deque`。

### 2.3 MVP 代码结构

```
prediction-market/
│
├── pyproject.toml                    # 项目配置
├── uv.lock / poetry.lock
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
│   │   ├── datetime_utils.py         # 时间工具
│   │   ├── redis_client.py           # Redis 连接 + 分布式锁 + Lua 脚本
│   │   └── database.py               # SQLAlchemy async 引擎 + Session
│   │
│   ├── pm_account/                   # ===== 模块 1: 账户模块 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # Account, Position, LedgerEntry (all int cents)
│   │   │   ├── enums.py              # AccountStatus, EntryType
│   │   │   ├── events.py             # BalanceFrozen, BalanceReleased, Netted
│   │   │   ├── service.py            # AccountDomainService
│   │   │   └── repository.py         # AccountRepository (Protocol)
│   │   ├── infrastructure/
│   │   │   ├── db_models.py          # ORM (BIGINT 字段)
│   │   │   ├── persistence.py        # SQLAlchemy 实现
│   │   │   └── cache.py              # Redis 余额缓存 + Lua 冻结
│   │   ├── application/
│   │   │   ├── schemas.py            # Pydantic (cents ↔ display 转换)
│   │   │   └── service.py            # AccountAppService
│   │   └── api/
│   │       └── router.py
│   │
│   ├── pm_market/                    # ===== 模块 2: 市场配置 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Market (price range: 1-99 int)
│   │   │   └── enums.py              # MarketStatus
│   │   ├── config/markets.json
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── api/router.py
│   │
│   ├── pm_order/                     # ===== 模块 3: 订单模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Order (price: int cents, quantity: int)
│   │   │   ├── enums.py              # OrderSide, OrderType, OrderStatus, TIF
│   │   │   ├── events.py
│   │   │   ├── service.py            # OrderDomainService
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
│   │   │   ├── balance_check.py      # available_cents >= price * qty
│   │   │   ├── order_limit.py        # 单笔 <= 1_000_000 cents ($10K)
│   │   │   ├── position_limit.py     # 单市场 <= 2_500_000 cents ($25K)
│   │   │   ├── market_status.py
│   │   │   └── price_range.py        # 1 <= price <= 99
│   │   ├── application/service.py
│   │   └── api/router.py
│   │
│   ├── pm_matching/                  # ===== 模块 5: 撮合引擎 ⭐ =====
│   │   ├── domain/
│   │   │   ├── models.py             # MatchResult, Trade
│   │   │   └── events.py             # TradeExecuted
│   │   ├── engine/
│   │   │   ├── order_book.py         # OrderBook: list[deque] O(1) 定长数组
│   │   │   ├── matching_algo.py      # 价格优先-时间优先
│   │   │   ├── market_router.py      # Dict[str, OrderBook]
│   │   │   └── engine.py             # MatchingEngine (同步调用, 无 Queue)
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── api/router.py             # GET /orderbook/{market_id}
│   │
│   ├── pm_clearing/                  # ===== 模块 6: 清算模块 =====
│   │   ├── domain/
│   │   │   ├── models.py             # Trade, Settlement, Fee (all int cents)
│   │   │   ├── service.py            # ClearingDomainService
│   │   │   ├── netting.py            # ⭐ AutoNettingService
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
│   │   │   ├── dependencies.py       # Depends(get_current_user)
│   │   │   └── password.py           # bcrypt
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
│   │   ├── test_account_domain.py
│   │   ├── test_order_domain.py
│   │   ├── test_risk_rules.py
│   │   ├── test_matching_engine.py   # ⭐ 撮合核心 12+ 场景
│   │   ├── test_clearing_domain.py
│   │   └── test_auto_netting.py      # ⭐ 净额结算测试
│   ├── integration/
│   └── e2e/
│       ├── test_full_trading_flow.py
│       ├── test_netting_flow.py      # ⭐ netting E2E
│       └── test_error_scenarios.py
│
├── config/settings.py
├── infrastructure/docker/
├── scripts/
├── docs/
├── Dockerfile
├── .env.example
├── Makefile
└── mypy.ini
```

### 2.4 数据库表设计（全整数化）

```sql
-- 所有金额字段使用 BIGINT, 单位：美分 (cents)

CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) UNIQUE NOT NULL,
    available_balance BIGINT NOT NULL DEFAULT 0,    -- 可用余额 (美分)
    frozen_balance BIGINT NOT NULL DEFAULT 0,       -- 冻结余额 (美分)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version BIGINT DEFAULT 0                        -- 乐观锁
);

CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    contract_type VARCHAR(10) NOT NULL,             -- YES / NO
    quantity INT NOT NULL DEFAULT 0,                -- 合约份数
    avg_entry_price INT NOT NULL DEFAULT 0,         -- 平均入场价 (美分)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, market_id, contract_type)
);

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id VARCHAR(64) UNIQUE NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    contract_type VARCHAR(10) NOT NULL,             -- YES / NO
    side VARCHAR(10) NOT NULL,                      -- BUY / SELL
    order_type VARCHAR(20) NOT NULL,                -- LIMIT
    time_in_force VARCHAR(10) NOT NULL,             -- GTC / IOC
    price INT NOT NULL,                             -- 价格 (1-99 美分)
    quantity INT NOT NULL,                          -- 合约份数
    filled_quantity INT DEFAULT 0,
    remaining_quantity INT NOT NULL,                -- 剩余未成交数量
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    market_id VARCHAR(64) NOT NULL,
    maker_order_id UUID NOT NULL,
    taker_order_id UUID NOT NULL,
    maker_user_id VARCHAR(64) NOT NULL,
    taker_user_id VARCHAR(64) NOT NULL,
    price INT NOT NULL,                             -- 成交价 (美分)
    quantity INT NOT NULL,                          -- 成交数量
    maker_side VARCHAR(10) NOT NULL,
    contract_type VARCHAR(10) NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    entry_type VARCHAR(30) NOT NULL,                -- DEPOSIT/WITHDRAW/TRADE/FEE/NETTING
    amount BIGINT NOT NULL,                         -- 金额 (美分), 正=入账, 负=出账
    balance_after BIGINT NOT NULL,                  -- 交易后余额 (美分)
    reference_id VARCHAR(64),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reserve 系统托管账户 (特殊 user_id = 'SYSTEM_RESERVE')
-- 所有交易对手方资金在此托管, Auto-Netting 从此释放
```

### 2.5 核心交易流程（整数化 + 同步撮合 + Netting）

```
用户 A: 买 YES 100份 @60美分
用户 B: 卖 YES 100份 @55美分 (挂单中)

=== 新订单到达 ===

1. [API] POST /orders → FastAPI 接收请求
2. [Lock] async with matching_lock:
3.   [Transaction] async with session.begin():
4.     [Risk] 风控检查:
          - A 余额 >= 60 * 100 = 6000 美分? ✅
          - 价格 1 <= 60 <= 99? ✅
          - 单笔 <= 1,000,000 美分? ✅
5.     [Freeze] 冻结 A 的 6000 美分
6.     [Match] 撮合: A买@60 vs B卖@55 → 以 maker 价 55 成交
          成交价: 55 美分, 数量: 100
7.     [Clear] 清算:
          A (买方): 解冻 6000, 扣款 55*100=5500 + fee, 获得 100 YES
          B (卖方): 解冻 (之前冻结的), 获得 5500 - fee
          Reserve: 收入对应金额
          多冻结的 500 美分 (6000-5500) 退回 A 的 available
8.     [Netting] Auto-Netting 检查:
          A 的 YES 持仓: 100, NO 持仓: 0 → nettable = 0, 跳过
9.     [Ledger] 写入流水 (TRADE + FEE)
10.  [Commit] 事务提交
11. [Unlock] 释放 matching_lock
12. [Response] 返回订单结果
```

---

### 2.6 MVP 模块实现顺序与详细步骤

---

#### 模块 0：项目脚手架与基础设施（第 1 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 0.1 | 初始化 Git 仓库 + 完整目录骨架 | 目录结构, .gitignore |
| 0.2 | 配置 pyproject.toml (依赖: fastapi, uvicorn, uvloop, sqlalchemy[asyncio], asyncpg, redis, pydantic, python-jose, bcrypt, alembic, pytest, httpx, ruff, mypy) | pyproject.toml |
| 0.3 | 配置开发工具链 | mypy.ini (strict), ruff.toml, .pre-commit-config.yaml |
| 0.4 | Docker Compose | docker-compose.yml (PostgreSQL 16 + Redis 7) |
| 0.5 | SQLAlchemy async 引擎 + Alembic | database.py, alembic.ini, env.py |
| 0.6 | 数据库迁移: 全部核心表 (BIGINT 整数化) | alembic/versions/001_initial.py |
| 0.7 | Pydantic Settings (.env 驱动) | config/settings.py |
| 0.8 | Makefile | `make dev`, `make test`, `make migrate`, `make lint` |
| 0.9 | CI 配置 | .github/workflows/ci.yml |

**验收标准**: `docker-compose up -d && make migrate && make dev` → Swagger 可访问。

---

#### 模块 1：pm_common 公共模块（第 1–2 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.1 | ApiResponse[T] 统一响应 | response.py |
| 1.2 | 错误码 + 自定义异常 | errors.py: ErrorCode, BusinessError, NotFoundError |
| 1.3 | 全局异常处理 (FastAPI exception_handler) | → 在 main.py 中注册 |
| 1.4 | Snowflake ID 生成器 | id_generator.py |
| 1.5 | **美分工具模块** | cents.py |

```python
# pm_common/cents.py
def validate_price(price_cents: int) -> None:
    """校验价格在 [1, 99] 范围内"""
    if not (1 <= price_cents <= 99):
        raise BusinessError(ErrorCode.INVALID_PRICE, f"Price must be 1-99, got {price_cents}")

def cents_to_display(cents: int) -> str:
    """美分转显示金额: 6000 → '$60.00'"""
    return f"${cents / 100:.2f}"

def calculate_cost(price_cents: int, quantity: int) -> int:
    """计算订单成本 (美分)"""
    return price_cents * quantity

def calculate_fee(amount_cents: int, fee_bps: int) -> int:
    """计算手续费 (基点制, 1 bp = 0.01%)
    fee_bps=20 → 0.20% → amount * 20 // 10000
    """
    return amount_cents * fee_bps // 10000
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.6 | Redis 客户端封装 (连接池 + Lock + Lua) | redis_client.py |
| 1.7 | 数据库会话管理 | database.py: get_db dependency |
| 1.8 | 单元测试 | tests/unit/test_common.py |

**验收标准**: `pytest tests/unit/test_common.py` 全绿; `mypy src/pm_common/ --strict` 零错误。

---

#### 模块 2：pm_account 账户模块（第 2–3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 2.1 | 文档 | docs/account-design.md |
| 2.2 | 领域模型 (全 int) | domain/models.py: Account(available_cents, frozen_cents), Position(quantity), LedgerEntry(amount_cents) |
| 2.3 | 枚举 | domain/enums.py: EntryType 增加 NETTING 类型 |
| 2.4 | 仓储接口 (Protocol) | domain/repository.py |
| 2.5 | AccountDomainService | domain/service.py |
| | ① deposit(user_id, amount_cents) | |
| | ② withdraw(user_id, amount_cents) | |
| | ③ freeze(user_id, amount_cents) → bool | |
| | ④ unfreeze(user_id, amount_cents) | |
| | ⑤ transfer(from_user, to_user, amount_cents) | |
| | ⑥ update_position(user_id, market_id, contract_type, qty_delta) | |
| 2.6 | ORM 模型 (BIGINT) | infrastructure/db_models.py |
| 2.7 | SQLAlchemy 实现 | infrastructure/persistence.py |
| 2.8 | Redis 缓存 + Lua 原子冻结 | infrastructure/cache.py |

**Redis Lua 脚本（整数版）：**
```lua
-- 原子冻结 (全整数, 无浮点)
local available = tonumber(redis.call('HGET', KEYS[1], 'available'))
local amount = tonumber(ARGV[1])
if available >= amount then
    redis.call('HINCRBY', KEYS[1], 'available', -amount)  -- HINCRBY 替代 HINCRBYFLOAT
    redis.call('HINCRBY', KEYS[1], 'frozen', amount)
    return 1
else
    return 0
end
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 2.9 | 应用层 + Pydantic Schemas (cents ↔ display) | application/ |
| 2.10 | REST API | api/router.py |
| 2.11 | 单元测试 | 冻结/解冻、溢出、乐观锁冲突 |
| 2.12 | 集成测试 | DB + Redis + API |

**Pydantic 显示层转换示例：**
```python
class BalanceResponse(BaseModel):
    available_cents: int          # 内部用: 6000
    frozen_cents: int
    available_display: str = ""   # API 返回: "$60.00"

    @model_validator(mode='after')
    def compute_display(self) -> 'BalanceResponse':
        self.available_display = cents_to_display(self.available_cents)
        return self
```

**验收标准**: 充值→查余额→冻结→解冻→查流水, 全整数链路跑通。

---

#### 模块 3：pm_market 市场配置（第 3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 3.1 | Market 模型 (价格: int 1-99) | domain/models.py |
| 3.2 | 市场状态枚举 | domain/enums.py |
| 3.3 | 静态配置 JSON | config/markets.json |

```json
[
  {
    "id": "MKT-BTC-100K-2026",
    "title": "Will BTC reach $100K by end of 2026?",
    "status": "ACTIVE",
    "contract_types": ["YES", "NO"],
    "min_price_cents": 1,
    "max_price_cents": 99,
    "tick_size_cents": 1,
    "max_position_per_user": 25000,
    "maker_fee_bps": 10,
    "taker_fee_bps": 20,
    "resolution_date": "2026-12-31T23:59:59Z"
  }
]
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 3.4 | MarketConfigService | application/service.py |
| 3.5 | REST API | api/router.py |
| 3.6 | 测试 | tests/ |

**验收标准**: GET /markets 返回市场列表, 所有价格字段为整数美分。

---

#### 模块 4：pm_order 订单模块（第 3–4 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.1 | 文档 + 状态机设计 | docs/order-design.md |
| 4.2 | 枚举 | OrderSide, OrderType, OrderStatus, TimeInForce |
| 4.3 | Order 领域模型 (price: int, quantity: int) | domain/models.py |

```python
@dataclass
class Order:
    id: str
    client_order_id: str
    market_id: str
    user_id: str
    contract_type: str      # YES / NO
    side: str               # BUY / SELL
    price: int              # 1-99 cents
    quantity: int            # 合约份数
    filled_quantity: int = 0
    remaining_quantity: int = 0
    status: OrderStatus = OrderStatus.NEW

    def __post_init__(self):
        self.remaining_quantity = self.quantity
        validate_price(self.price)

    def fill(self, qty: int) -> None:
        """部分/全部成交"""
        self.filled_quantity += qty
        self.remaining_quantity -= qty
        if self.remaining_quantity == 0:
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.4 | 状态机 (严格流转) | 内嵌在 Order 模型中 |
| 4.5 | 领域事件 | domain/events.py |
| 4.6 | 仓储接口 + 实现 | domain/repository.py + infrastructure/ |
| 4.7 | 应用层 | application/ |
| 4.8 | REST API | POST /orders, DELETE /orders/{id}, GET /orders |
| 4.9 | 单元测试 | 状态机, 幂等, 价格校验(必须 1-99 整数) |
| 4.10 | 集成测试 | 下单→入库→查询 |

**验收标准**: 创建→查询→取消; 重复 client_order_id 返回已存在; price=0 或 100 被拒绝。

---

#### 模块 5：pm_risk 风控模块（第 4–5 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 5.1 | 文档 | docs/risk-rules.md |
| 5.2 | RiskRule Protocol + RiskCheckResult | domain/ |
| 5.3 | balance_check.py | available_cents >= price * quantity |
| 5.4 | order_limit.py | price * quantity <= 1_000_000 cents ($10K) |
| 5.5 | position_limit.py | 现有持仓 + 新单 <= 2_500_000 cents ($25K) |
| 5.6 | market_status.py | market.status == ACTIVE |
| 5.7 | price_range.py | 1 <= price <= 99 (整数) |
| 5.8 | RiskDomainService (规则链) | domain/service.py |
| 5.9 | RiskCheckService (联动 Account) | application/service.py |
| 5.10 | 单元测试 | 每条规则 pass/reject |
| 5.11 | 集成测试 | 下单→风控→冻结 |

**验收标准**: 余额不足→拒绝; 超限额→拒绝; price=0→拒绝; 正常→通过并冻结。

---

#### 模块 6：pm_matching 撮合引擎（第 5–7 周）⭐ 核心难点

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.1 | 文档 | docs/matching-engine-design.md |
| 6.2 | **O(1) 订单簿** | engine/order_book.py |

```python
from collections import deque
from dataclasses import dataclass, field

@dataclass
class OrderBook:
    market_id: str
    contract_type: str  # YES 或 NO

    # index 0 废弃; index 1-99 对应价格 1-99 美分
    bids: list[deque] = field(default_factory=lambda: [deque() for _ in range(100)])
    asks: list[deque] = field(default_factory=lambda: [deque() for _ in range(100)])

    # 缓存最优价格, 避免每次遍历
    best_bid: int = 0    # 最高买价, 0 = 无买单
    best_ask: int = 100  # 最低卖价, 100 = 无卖单

    def add_bid(self, order: Order) -> None:
        self.bids[order.price].append(order)
        if order.price > self.best_bid:
            self.best_bid = order.price

    def add_ask(self, order: Order) -> None:
        self.asks[order.price].append(order)
        if order.price < self.best_ask:
            self.best_ask = order.price

    def _refresh_best_bid(self) -> None:
        """从当前 best_bid 向下扫描找到下一个非空档位"""
        while self.best_bid > 0 and not self.bids[self.best_bid]:
            self.best_bid -= 1

    def _refresh_best_ask(self) -> None:
        """从当前 best_ask 向上扫描找到下一个非空档位"""
        while self.best_ask < 100 and not self.asks[self.best_ask]:
            self.best_ask += 1

    def get_depth(self, levels: int = 10) -> dict:
        """返回买卖 N 档深度"""
        bid_depth, ask_depth = [], []
        p = self.best_bid
        while p > 0 and len(bid_depth) < levels:
            if self.bids[p]:
                total_qty = sum(o.remaining_quantity for o in self.bids[p])
                bid_depth.append({"price": p, "quantity": total_qty})
            p -= 1
        p = self.best_ask
        while p < 100 and len(ask_depth) < levels:
            if self.asks[p]:
                total_qty = sum(o.remaining_quantity for o in self.asks[p])
                ask_depth.append({"price": p, "quantity": total_qty})
            p += 1
        return {"bids": bid_depth, "asks": ask_depth}
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.3 | 撮合算法 (价格优先-时间优先) | engine/matching_algo.py |

```python
def match_order(book: OrderBook, taker: Order) -> list[Trade]:
    """核心撮合逻辑, 全整数运算"""
    trades: list[Trade] = []

    if taker.side == "BUY":
        # 买单: 从最低卖价开始撮合
        while taker.remaining_quantity > 0 and book.best_ask <= taker.price:
            price_level = book.asks[book.best_ask]
            while price_level and taker.remaining_quantity > 0:
                maker = price_level[0]
                fill_qty = min(taker.remaining_quantity, maker.remaining_quantity)
                fill_price = maker.price  # 以 maker 价成交

                trades.append(Trade(
                    maker_order=maker, taker_order=taker,
                    price=fill_price, quantity=fill_qty
                ))

                taker.fill(fill_qty)
                maker.fill(fill_qty)
                if maker.remaining_quantity == 0:
                    price_level.popleft()

            book._refresh_best_ask()

        # 剩余未成交部分挂入买方订单簿
        if taker.remaining_quantity > 0 and taker.time_in_force == "GTC":
            book.add_bid(taker)
        elif taker.remaining_quantity > 0 and taker.time_in_force == "IOC":
            taker.cancel()

    # SELL 侧对称逻辑...
    return trades
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.4 | 市场路由 | engine/market_router.py: Dict[market_id, Dict[contract_type, OrderBook]] |
| 6.5 | **MatchingEngine (同步调用, 无 Queue)** | engine/engine.py |

```python
class MatchingEngine:
    """撮合引擎 — 无 Queue, 由请求直接同步调用"""
    def __init__(self):
        self.books: dict[str, dict[str, OrderBook]] = {}

    def get_or_create_book(self, market_id: str, contract_type: str) -> OrderBook:
        ...

    def submit_order(self, order: Order) -> list[Trade]:
        """同步撮合, 返回成交列表. 在 matching_lock 保护下调用."""
        book = self.get_or_create_book(order.market_id, order.contract_type)
        return match_order(book, order)

    def cancel_order(self, market_id: str, contract_type: str, order_id: str) -> bool:
        ...
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.6 | 应用层 | application/service.py |
| 6.7 | API (订单簿深度查询) | api/router.py |
| 6.8 | **单元测试 (12+ 场景)** | tests/unit/test_matching_engine.py |

**撮合测试场景 (全整数)：**

| # | 场景 | 预期 |
|---|------|------|
| 1 | BUY 100@60 vs SELL 100@60 | 成交 100@60 |
| 2 | BUY@65 vs SELL@55 | 以 maker 价 55 成交 |
| 3 | BUY 100@60 vs SELL 50@60 | 成交 50, 买方剩 50 挂单 |
| 4 | BUY 200@65 vs [SELL 50@55, SELL 80@60, SELL 100@65] | 3 笔成交 |
| 5 | IOC 买 200@60 但只有 SELL 50@60 | 成交 50, 剩余 150 取消 |
| 6 | 空簿下 BUY@60 | 直接挂入 bids[60] |
| 7 | 取消挂单 | 从 deque 移除 |
| 8 | best_bid / best_ask 缓存正确 | 撮合后缓存自动更新 |
| 9 | 同价格时间优先 | 先到的 maker 先成交 |
| 10 | BUY@50 vs SELL@60 | 不交叉, 双方挂单 |
| 11 | YES 和 NO 独立订单簿 | 互不干扰 |
| 12 | 边界: BUY@99 vs SELL@1 | 以 maker 价成交 |

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.9 | 性能基准测试 | tests/performance/bench_matching.py |

**验收标准**: 12 场景全绿; 性能 >3k ops/sec (纯 Python int + list)。

---

#### 模块 7：pm_clearing 清算模块（第 7–8 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.1 | 文档 | docs/clearing-design.md |
| 7.2 | Trade, Settlement 模型 (全 int) | domain/models.py |
| 7.3 | ORM | infrastructure/db_models.py |
| 7.4 | **清算核心逻辑 (整数化)** | domain/service.py |

**清算流程 (每笔 Trade)：**
```python
async def settle_trade(trade: Trade, session: AsyncSession):
    cost_cents = trade.price * trade.quantity  # 全整数
    maker_fee = calculate_fee(cost_cents, market.maker_fee_bps)  # 整数
    taker_fee = calculate_fee(cost_cents, market.taker_fee_bps)  # 整数

    # === 买方(taker) ===
    # 解冻: 之前冻结的 taker.price * qty (可能 > 实际成交价)
    await unfreeze(taker_user, taker.price * trade.quantity)
    # 扣款: 实际成交 cost + fee
    await debit(taker_user, cost_cents + taker_fee)
    # 加持仓
    await add_position(taker_user, market_id, contract_type, trade.quantity)

    # === 卖方(maker) ===
    # 如果是持仓卖出: 扣减持仓
    await reduce_position(maker_user, market_id, contract_type, trade.quantity)
    # 入账: 成交金额 - fee
    await credit(maker_user, cost_cents - maker_fee)

    # === Reserve ===
    # 手续费入 reserve
    await credit_reserve(maker_fee + taker_fee)

    # === 流水 ===
    await write_ledger(taker_user, "TRADE", -(cost_cents + taker_fee))
    await write_ledger(maker_user, "TRADE", cost_cents - maker_fee)
    await write_ledger(taker_user, "FEE", -taker_fee)
    await write_ledger(maker_user, "FEE", -maker_fee)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.5 | **⭐ Auto-Netting 净额结算** | domain/netting.py |

```python
async def auto_netting(user_id: str, market_id: str, session: AsyncSession):
    """
    每次成交后调用。检查用户是否同时持有 YES 和 NO，
    若有则自动销毁等量双边头寸并释放资金。

    YES + NO 各 1 份 = 确定性 $1.00 回报 = 100 美分
    """
    yes_pos = await get_position(user_id, market_id, "YES", session)
    no_pos = await get_position(user_id, market_id, "NO", session)

    yes_qty = yes_pos.quantity if yes_pos else 0
    no_qty = no_pos.quantity if no_pos else 0
    nettable = min(yes_qty, no_qty)

    if nettable <= 0:
        return

    # 销毁等量双边持仓
    yes_pos.quantity -= nettable
    no_pos.quantity -= nettable

    # 释放资金: 每对 = 100 cents
    release_cents = nettable * 100
    await credit_user(user_id, release_cents, session)
    await debit_reserve(release_cents, session)

    # 记录流水
    await write_ledger(user_id, "NETTING", release_cents, session,
                       description=f"Auto-netting {nettable} pairs in {market_id}")
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.6 | 事务保证 | 清算+Netting 在同一个 session.begin() 中 |
| 7.7 | 应用层 | application/service.py |
| 7.8 | REST API (成交查询) | api/router.py |
| 7.9 | 单元测试 | 费用计算(整数)、余额变化 |
| 7.10 | **Netting 测试** | tests/unit/test_auto_netting.py |

**Netting 测试场景：**

| # | 场景 | 预期 |
|---|------|------|
| 1 | 持有 100 YES + 0 NO | nettable=0, 无操作 |
| 2 | 持有 100 YES + 100 NO | 销毁 100 对, 释放 10000 cents |
| 3 | 持有 50 YES + 100 NO | 销毁 50 对, 释放 5000 cents, 剩 50 NO |
| 4 | 连续买入 YES 然后买入 NO | 第二次成交后触发 netting |
| 5 | netting 后流水记录正确 | NETTING 类型, 金额正确 |

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.11 | 集成测试 | 撮合→清算→netting→余额+持仓+流水 |

**验收标准**: 买卖后余额变化正确; netting 自动触发; 零和验证通过。

---

#### 模块 8：pm_gateway 网关/认证（第 8–9 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 8.1 | User 模型 + ORM | user/ |
| 8.2 | bcrypt 密码哈希 | auth/password.py |
| 8.3 | JWT 生成/验证 | auth/jwt_handler.py |
| 8.4 | FastAPI Depends(get_current_user) | auth/dependencies.py |
| 8.5 | 注册/登录 API | api/router.py |
| 8.6 | 令牌桶限流中间件 | middleware/rate_limit.py |
| 8.7 | 请求日志 + 全局异常处理 | middleware/ |
| 8.8 | 所有业务 Router 加认证 | Depends(get_current_user) |
| 8.9 | 测试 | JWT, 密码哈希, 鉴权拦截 |

**验收标准**: 无 Token → 401; 登录 → Token → 可访问交易 API。

---

#### 模块 9：端到端集成（第 9–10 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.1 | main.py 串联所有模块 + uvloop | main.py |
| 9.2 | **核心交易链路集成** | 整合 matching_lock 同步流程 |

```python
# 核心交易入口（在 OrderAppService 中）
matching_lock = asyncio.Lock()
matching_engine = MatchingEngine()

async def place_order_flow(cmd: PlaceOrderCmd, user: User, session: AsyncSession):
    async with matching_lock:
        async with session.begin():
            # 1. 创建订单
            order = Order.create(cmd)
            # 2. 风控检查 + 余额冻结
            risk_result = await risk_service.check_and_freeze(order, session)
            if not risk_result.passed:
                return OrderResult.rejected(risk_result)
            # 3. 同步撮合
            trades = matching_engine.submit_order(order)
            # 4. 持久化订单
            await order_repo.save(order, session)
            # 5. 逐笔清算
            for trade in trades:
                await clearing_service.settle_trade(trade, session)
                # 6. Auto-Netting
                await netting_service.auto_netting(trade.taker_user_id, trade.market_id, session)
                await netting_service.auto_netting(trade.maker_user_id, trade.market_id, session)
            # 7. 持久化成交
            await trade_repo.save_all(trades, session)
        # 事务提交, 锁释放
    return OrderResult.accepted(order, trades)
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.3 | E2E 完整流程测试 | tests/e2e/test_full_trading_flow.py |

**E2E 完整流程 (整数化)：**
```
1. 注册用户 A, B
2. A 充值 1_000_000 cents ($10,000)
3. B 充值 1_000_000 cents ($10,000)
4. A 买 YES 100@60 → 冻结 6000 cents
5. B 卖 YES 100@55 → 挂单
6. A 买 YES 100@55 → 与 B 撮合 @55
7. 验证 A: 余额减少 5500+fee, 持仓 +100 YES
8. 验证 B: 余额增加 5500-fee
9. B 买 NO 100@40 → 假设有人挂卖
10. 验证 Netting: B 同时持有 YES 和 NO → 自动结算
11. 零和验证: sum(all users) + reserve == 初始总充值
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.4 | Netting E2E 测试 | tests/e2e/test_netting_flow.py |
| 9.5 | 异常场景测试 | tests/e2e/test_error_scenarios.py |
| 9.6 | **零和验证脚本** | scripts/verify_consistency.py |

```python
async def verify_zero_sum(session: AsyncSession):
    """验证系统资金守恒: 所有用户资金 + Reserve = 总充值"""
    total_user_balance = await sum_all_user_balances(session)  # available + frozen
    total_reserve = await get_reserve_balance(session)
    total_deposits = await sum_all_deposits(session)
    total_withdrawals = await sum_all_withdrawals(session)

    expected = total_deposits - total_withdrawals
    actual = total_user_balance + total_reserve

    assert actual == expected, f"资金不守恒! expected={expected}, actual={actual}"
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.7 | Dockerfile (多阶段构建) | Dockerfile |
| 9.8 | docker-compose.full.yml | 一键启动全部 |
| 9.9 | Seed 数据脚本 | scripts/seed_data.py |

**验收标准**: `docker-compose up` → `pytest tests/ -v` 全绿 → 零和验证通过。

---

### 2.7 MVP 里程碑

```
Week 1:   [脚手架 + pm_common] ── Docker、DB(BIGINT)、cents工具、uvloop
Week 2-3: [pm_account] ────────── 充值/冻结/流水 (全整数)
Week 3:   [pm_market] ─────────── 市场配置 (价格 1-99 int)
Week 4:   [pm_order] ──────────── 下单/状态机 (price: int)
Week 5:   [pm_risk] ───────────── 风控规则链 (整数比较)
Week 6-7: [pm_matching] ──────── O(1) 定长数组撮合引擎 ⭐
Week 8:   [pm_clearing] ────────── 整数清算 + Auto-Netting ⭐
Week 9:   [pm_gateway] ─────────── JWT 认证 + 限流
Week 10:  [E2E + 发布] ─────────── matching_lock 集成 + 零和验证 🎉
```

---

## 三、Phase 2 — 中期实施计划

### 3.1 核心目标
微服务拆分 + 市场管理 + 行情 + 预言机 + 监控。

### 3.2 实施顺序

| 优先级 | 模块 | 关键变更 | 预计周期 |
|--------|------|----------|----------|
| **P0** | 基础设施升级 | Kafka (Redpanda) + Consul | 2 周 |
| **P0** | 微服务拆分 | 每个 pm_* → 独立 FastAPI; matching_lock → 分布式锁 | 3 周 |
| **P1** | pm-market-service | 市场生命周期状态机 + CRUD + 结算触发 | 2 周 |
| **P1** | pm-oracle-service | 数据采集 + 人工裁决 + 市场结算 | 2 周 |
| **P2** | pm-market-data-service | TimescaleDB K线 + WebSocket 推送 | 2 周 |
| **P2** | pm-notification-service | Kafka 消费 + WebSocket 通知 | 2 周 |
| **P3** | API Gateway (Kong/Traefik) | 替换内嵌路由 | 1 周 |
| **P3** | 监控 (Prometheus + Grafana + Jaeger) | 可观测性 | 2 周 |

### 3.3 微服务拆分关键变更

```
MVP (单进程 + matching_lock)         中期 (多服务)
──────────────────────                ────────────
asyncio.Lock()                  →    Redis 分布式锁 (Redlock)
直接方法调用                     →    HTTP/gRPC 内部 API
单进程内存 OrderBook             →    独立 matching 服务 (内存 OrderBook)
session.begin() 单事务           →    Saga 模式 (最终一致性)
```

---

## 四、Phase 3 — 生产就绪计划

| 优先级 | 模块 | 关键升级 |
|--------|------|----------|
| **P0** | 撮合引擎重写 | Java + LMAX Disruptor 或 Rust (如需 >10k TPS) |
| **P0** | 数据库高可用 | PostgreSQL 主从 + 连接池 |
| **P0** | K8s 部署 | 多副本 + 自动故障转移 |
| **P1** | 合成撮合 | YES+NO 对冲下单逻辑 |
| **P1** | 市场结算 | 裁决后 YES=100/NO=0, 强制平仓, Reserve 清算 |
| **P1** | 智能风控 | 规则引擎 + 反操纵检测 |
| **P2** | 分析系统 | ClickHouse + 对账 + 反作弊 |
| **P2** | 审计合规 | 不可篡改日志 |

---

## 五、每个模块通用的 Python 实施模板

```
┌──────────────────────────────────────────────────────────────┐
│               Python 模块实施标准流程                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 📋 需求与设计                                             │
│     ├── 设计文档 (接口、数据模型、流程图)                       │
│     ├── Pydantic Schema (cents ↔ display 转换在此层)          │
│     └── 数据库表 (BIGINT, Alembic migration)                  │
│                                                              │
│  2. 🏗️ 领域层 (domain/) — 全 int, 无 IO                      │
│     ├── models.py — dataclass (price: int, amount: int)       │
│     ├── enums.py                                              │
│     ├── events.py                                             │
│     ├── service.py — 纯计算逻辑                               │
│     └── repository.py — Protocol                              │
│                                                              │
│  3. 🔧 基础设施层 (infrastructure/)                            │
│     ├── db_models.py — SQLAlchemy (Column(BigInteger))        │
│     ├── persistence.py                                        │
│     └── cache.py — Redis (HINCRBY, 非 HINCRBYFLOAT)          │
│                                                              │
│  4. 🖥️ 应用层 (application/)                                  │
│     ├── schemas.py — Pydantic (cents 内部, display 输出)      │
│     └── service.py — 编排                                     │
│                                                              │
│  5. 🌐 API 层 — FastAPI Router                                │
│                                                              │
│  6. ✅ 测试 — pytest (所有断言基于 int 比较, 无精度问题)        │
│                                                              │
│  7. 🔍 质量: mypy --strict + ruff + pytest --cov ≥80%         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、快速参考 — 一页纸行动清单

```
Phase 1 — Python MVP (8-12 周):
  □ Week 1:   脚手架 + pm_common (BIGINT + cents 工具 + uvloop)
  □ Week 2-3: pm_account (整数余额/冻结/流水)
  □ Week 3:   pm_market (价格 1-99 整数)
  □ Week 4:   pm_order (int price + 状态机)
  □ Week 5:   pm_risk (整数比较规则链)
  □ Week 6-7: pm_matching (O(1) list[deque] 订单簿) ⭐
  □ Week 8:   pm_clearing (整数清算 + Auto-Netting) ⭐
  □ Week 9:   pm_gateway (JWT + 限流)
  □ Week 10:  E2E (matching_lock + 零和验证) 🎉

Phase 2 — 微服务 (10-16 周):
  □ Kafka + Consul
  □ 拆分为独立 FastAPI 服务
  □ Market / Oracle / MarketData / Notification
  □ Kong + Prometheus + Grafana 🎉

Phase 3 — 生产就绪 (12-20 周):
  □ 撮合引擎 Java/Rust 重写
  □ 合成撮合 + 市场结算
  □ K8s HA + 分析 + 审计 🚀
```

---

## 附录：v2 → v3 修正对照表

| 原设计 (v2) | 修正后 (v3) | 理由 |
|-------------|-------------|------|
| `Decimal` / `NUMERIC` | `int` / `BIGINT` (美分) | 价格 1-99 是天然整数; int 快 20-50x |
| `SortedDict` O(log N) | `list[deque]` O(1) 定长 100 | 价格空间有限, 数组直接寻址 |
| `asyncio.Queue` 解耦 | `asyncio.Lock` 请求内同步 | AsyncSession 不能跨协程 |
| 无 Auto-Netting | 每笔成交后强制 Netting | 防止资金锁死, Reserve 正确性 |
| 标准 asyncio | uvloop | I/O 性能提升 2-4x |
| `HINCRBYFLOAT` | `HINCRBY` | 全整数, Redis 也用整数操作 |
| 无 Reserve 账户 | SYSTEM_RESERVE 托管池 | 资金守恒的对手方 |

---

*文档版本: v3.0 (整合二元市场核心设计修正) | 生成日期: 2026-02-20*
