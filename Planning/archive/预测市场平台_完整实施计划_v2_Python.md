# 预测市场平台 — 完整实施计划 (Python MVP 版)

> **版本**: v2.0 — Python MVP
> **目标读者**: 独立开发者，借助 AI Vibe Coding 逐步实现
> **核心变更**: MVP 全部使用 Python，保持模块化设计，支持将来逐模块替换为 Java/Rust
> **日期**: 2026-02-20

---

## 一、总体阶段划分

| 阶段 | 核心目标 | 预计周期 | 服务形态 | 关键技术 |
|------|----------|----------|----------|----------|
| **Phase 1 — MVP** | 验证核心交易链路：下单→风控→撮合→清算→记账 | 8–12 周 | Python 单体（模块化） | FastAPI, SQLAlchemy, PostgreSQL, Redis |
| **Phase 2 — 中期** | 微服务拆分 + 市场管理 + 行情 + 预言机 + 监控 | 10–16 周 | Python 微服务（核心链路可选 Java 重写） | Kafka, Consul, TimescaleDB, WebSocket |
| **Phase 3 — 生产就绪** | 高可用、性能关键模块 Java/Rust 重写、合规审计 | 12–20 周 | Python + Java/Rust 混合微服务 | K8s, Flink, Temporal, ClickHouse |

### 为什么 Python MVP 是合理的？

**优势：**
- 开发速度快，FastAPI 自带 Swagger 文档，极大缩短 API 开发周期
- Python 生态丰富，AI 代码生成对 Python 的支持最好
- 所有模块统一语言，降低心智负担
- Pydantic v2 的数据验证性能已大幅提升（Rust 内核）
- 对于 MVP 级别的并发（数百~数千 TPS），Python 完全胜任

**风险与应对：**
- 撮合引擎性能天花板：MVP 目标 1k–5k ops/sec（Python 可达），中期如需 >100k 再用 Java/Rust 重写
- GIL 限制并发：使用 asyncio 异步 I/O + 撮合引擎单线程（本就是最佳实践）
- 类型安全性：通过 Pydantic + mypy 严格模式弥补

**将来替换策略：**
```
Phase 1 (全 Python)     →  Phase 2 (拆分微服务)     →  Phase 3 (性能关键模块替换)
                              │                              │
pm_matching (Python)     →  pm-matching-service      →  Java/Rust 重写
pm_clearing (Python)     →  pm-clearing-service      →  Java 重写（可选）
pm_account (Python)      →  pm-account-service       →  保持 Python 或 Java
pm_risk (Python)         →  pm-risk-service          →  保持 Python 或 Java
```

关键点：只要每个模块的接口（输入/输出）定义清晰，替换语言就是内部实现的事。

---

## 二、Phase 1 — MVP 详细计划

### 2.1 MVP 包含的功能范围

**包含：**
- 用户账户：注册/登录（JWT）、充值/提现（模拟）、余额查询
- 市场：静态配置文件定义市场（暂不需要独立服务）
- 下单：限价单（GTC/IOC），买入 YES/NO 合约
- 风控：余额检查、单笔限额、持仓限额（硬编码规则）
- 撮合：单线程限价订单簿（LOB），YES/NO 独立撮合
- 清算：成交后资金划转、手续费扣除、持仓更新
- 查询：订单历史、持仓、账户流水

**不包含（推迟到中期/完备）：**
- 市场生命周期管理（创建、暂停、结算）
- 预言机裁决
- 实时行情推送（K线、深度图）
- 通知系统
- 合成撮合（YES+NO 对冲）
- 分布式消息队列（Kafka）
- 服务发现、配置中心
- 监控、链路追踪

### 2.2 MVP 技术栈

| 层次 | 技术选择 | 版本 | 说明 |
|------|----------|------|------|
| 语言 | Python | 3.12+ | 类型提示全覆盖 |
| Web 框架 | FastAPI | 0.109+ | 异步 + 自动 API 文档 |
| ASGI 服务器 | Uvicorn | 0.27+ | 生产用 Gunicorn + Uvicorn worker |
| 数据验证 | Pydantic | v2.5+ | Rust 内核，性能优秀 |
| ORM | SQLAlchemy | 2.0+ | 异步模式 (asyncio) |
| 数据库驱动 | asyncpg | 0.29+ | PostgreSQL 异步驱动 |
| 数据库 | PostgreSQL | 16 | 单实例，主账本 |
| 缓存 | Redis (redis-py) | 7 / 5.0+ | 余额缓存、分布式锁 |
| 有序数据结构 | sortedcontainers | 2.4+ | 撮合引擎订单簿 (替代 Java TreeMap) |
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
├── pyproject.toml                    # 项目配置 (uv / Poetry)
├── uv.lock / poetry.lock            # 依赖锁定
├── alembic.ini                       # 数据库迁移配置
├── alembic/                          # 迁移版本目录
│   └── versions/
│
├── src/
│   ├── pm_common/                    # ===== 模块 0: 公共模块 =====
│   │   ├── __init__.py
│   │   ├── errors.py                 # 统一错误码、自定义异常
│   │   ├── response.py               # Result[T] 统一响应封装
│   │   ├── id_generator.py           # Snowflake ID 生成器
│   │   ├── decimal_utils.py          # Decimal 精度工具
│   │   ├── datetime_utils.py         # 时间工具
│   │   ├── redis_client.py           # Redis 连接 + 分布式锁
│   │   └── database.py               # SQLAlchemy async 引擎 + Session
│   │
│   ├── pm_account/                   # ===== 模块 1: 账户模块 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── models.py             # Account, Position, LedgerEntry
│   │   │   ├── enums.py              # AccountStatus, EntryType
│   │   │   ├── events.py             # BalanceFrozen, BalanceReleased
│   │   │   ├── service.py            # AccountDomainService (核心逻辑)
│   │   │   └── repository.py         # AccountRepository (抽象接口)
│   │   ├── infrastructure/
│   │   │   ├── __init__.py
│   │   │   ├── persistence.py        # SQLAlchemy 实现
│   │   │   ├── db_models.py          # ORM 模型 (表映射)
│   │   │   └── cache.py              # Redis 余额缓存 + Lua 脚本
│   │   ├── application/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py            # Pydantic 请求/响应 Schema
│   │   │   └── service.py            # AccountAppService (用例编排)
│   │   └── api/
│   │       ├── __init__.py
│   │       └── router.py             # FastAPI Router (/accounts/*)
│   │
│   ├── pm_market/                    # ===== 模块 2: 市场配置 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # Market, MarketRule
│   │   │   └── enums.py              # MarketStatus
│   │   ├── config/
│   │   │   └── markets.json          # 静态市场配置
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py            # MarketConfigService
│   │   └── api/
│   │       └── router.py             # FastAPI Router (/markets/*)
│   │
│   ├── pm_order/                     # ===== 模块 3: 订单模块 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # Order (含状态机逻辑)
│   │   │   ├── enums.py              # OrderSide, OrderType, OrderStatus, TIF
│   │   │   ├── events.py             # OrderPlaced, OrderCancelled, OrderFilled
│   │   │   ├── service.py            # OrderDomainService
│   │   │   └── repository.py         # OrderRepository (抽象)
│   │   ├── infrastructure/
│   │   │   ├── persistence.py
│   │   │   └── db_models.py
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   ├── commands.py           # PlaceOrderCmd, CancelOrderCmd
│   │   │   └── service.py            # OrderAppService
│   │   └── api/
│   │       └── router.py             # FastAPI Router (/orders/*)
│   │
│   ├── pm_risk/                      # ===== 模块 4: 风控模块 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # RiskCheckResult
│   │   │   ├── rules.py              # 风控规则链 (Protocol/ABC)
│   │   │   └── service.py            # RiskDomainService
│   │   ├── rules/                    # 具体规则实现
│   │   │   ├── balance_check.py      # 余额充足检查
│   │   │   ├── order_limit.py        # 单笔限额
│   │   │   ├── position_limit.py     # 持仓限额
│   │   │   ├── market_status.py      # 市场状态检查
│   │   │   └── price_range.py        # 价格合理性检查
│   │   ├── application/
│   │   │   └── service.py            # RiskCheckService
│   │   └── api/
│   │       └── router.py             # (调试用)
│   │
│   ├── pm_matching/                  # ===== 模块 5: 撮合引擎 ⭐ =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # OrderBook, PriceLevel, MatchResult
│   │   │   ├── enums.py              # MatchType
│   │   │   └── events.py             # TradeExecuted
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── order_book.py         # OrderBook (SortedDict 实现)
│   │   │   ├── matching_algo.py      # 价格优先-时间优先撮合
│   │   │   ├── market_router.py      # 按 market_id 路由
│   │   │   └── engine.py             # MatchingEngine (asyncio.Queue)
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py            # MatchingEngineService
│   │   └── api/
│   │       └── router.py             # (深度/订单簿查询)
│   │
│   ├── pm_clearing/                  # ===== 模块 6: 清算模块 =====
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── models.py             # Trade, Settlement, Fee
│   │   │   ├── service.py            # ClearingDomainService
│   │   │   └── repository.py
│   │   ├── infrastructure/
│   │   │   ├── persistence.py
│   │   │   └── db_models.py
│   │   ├── application/
│   │   │   ├── schemas.py
│   │   │   └── service.py            # ClearingAppService
│   │   └── api/
│   │       └── router.py             # (成交查询)
│   │
│   ├── pm_gateway/                   # ===== 模块 7: 网关/认证 =====
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── jwt_handler.py        # JWT 生成/验证
│   │   │   ├── dependencies.py       # FastAPI Depends(get_current_user)
│   │   │   └── password.py           # bcrypt 密码哈希
│   │   ├── user/
│   │   │   ├── models.py             # User 模型
│   │   │   ├── db_models.py          # User ORM
│   │   │   ├── service.py            # UserService
│   │   │   └── schemas.py            # RegisterReq, LoginReq, LoginResp
│   │   ├── middleware/
│   │   │   ├── rate_limit.py         # 令牌桶限流
│   │   │   ├── request_log.py        # 请求日志
│   │   │   └── error_handler.py      # 全局异常处理
│   │   └── api/
│   │       └── router.py             # /auth/register, /auth/login
│   │
│   └── main.py                       # ===== FastAPI 应用入口 =====
│                                      # 注册所有 Router, 启动事件
│
├── tests/
│   ├── conftest.py                   # pytest fixtures (DB, Redis, Client)
│   ├── unit/                         # 单元测试
│   │   ├── test_account_domain.py
│   │   ├── test_order_domain.py
│   │   ├── test_risk_rules.py
│   │   ├── test_matching_engine.py   # ⭐ 撮合核心测试
│   │   └── test_clearing_domain.py
│   ├── integration/                  # 集成测试 (需要 DB + Redis)
│   │   ├── test_account_api.py
│   │   ├── test_order_api.py
│   │   └── test_clearing_flow.py
│   └── e2e/                          # 端到端测试
│       ├── test_full_trading_flow.py  # 注册→充值→下单→撮合→清算→查询
│       └── test_error_scenarios.py    # 异常场景
│
├── config/
│   ├── settings.py                   # Pydantic Settings (环境变量)
│   └── markets.json                  # 市场静态配置
│
├── infrastructure/
│   └── docker/
│       ├── docker-compose.yml        # PostgreSQL + Redis
│       └── docker-compose.full.yml   # 包含应用服务
│
├── scripts/
│   ├── setup.sh                      # 一键启动开发环境
│   ├── seed_data.py                  # 初始化测试数据
│   └── run_tests.sh                  # 运行全部测试
│
├── docs/
│   ├── api-overview.md
│   ├── account-design.md
│   ├── order-design.md
│   ├── matching-engine-design.md
│   ├── clearing-design.md
│   └── risk-rules.md
│
├── Dockerfile
├── .env.example
├── .gitignore
├── Makefile                          # 常用命令快捷方式
└── mypy.ini                          # 严格类型检查配置
```

### 2.4 关键设计模式：保持模块可替换性

为了将来能逐模块替换为其他语言，每个模块必须遵守以下原则：

**1. 接口隔离 — 使用 Python Protocol/ABC 定义模块边界**

```python
# pm_account/domain/repository.py
from typing import Protocol
from decimal import Decimal

class AccountRepository(Protocol):
    """账户仓储接口 — 这是模块的边界契约"""
    async def get_by_user_id(self, user_id: str) -> Account | None: ...
    async def freeze_balance(self, user_id: str, amount: Decimal) -> bool: ...
    async def release_balance(self, user_id: str, amount: Decimal) -> bool: ...
```

**2. 模块间通过 Application Service 通信，不直接访问其他模块的 Domain**

```python
# pm_order/application/service.py
class OrderAppService:
    def __init__(self,
                 risk_service: RiskCheckService,     # 依赖风控模块的应用层
                 matching_service: MatchingEngineService,  # 依赖撮合模块
                 order_repo: OrderRepository):
        ...

    async def place_order(self, cmd: PlaceOrderCmd) -> OrderResult:
        # 1. 创建订单
        order = Order.create(cmd)
        # 2. 风控检查 (调用风控模块)
        risk_result = await self.risk_service.check(order)
        if not risk_result.passed:
            return OrderResult.rejected(risk_result.reason)
        # 3. 提交撮合 (调用撮合模块)
        await self.matching_service.submit_order(order)
        # 4. 持久化
        await self.order_repo.save(order)
        return OrderResult.accepted(order)
```

**3. 将来替换时只需要：**
- 把某个模块变成独立服务（独立 FastAPI 应用或 Java 服务）
- 在原位置用 HTTP/gRPC 客户端替换直接方法调用
- 模块内部逻辑可以用任何语言重写

---

### 2.5 MVP 模块实现顺序与详细步骤

---

#### 模块 0：项目脚手架与基础设施（第 1 周）

| 步骤 | 具体任务 | 产出物 | AI 辅助要点 |
|------|----------|--------|-------------|
| 0.1 | 初始化 Git 仓库 + 目录结构 | 上述完整目录骨架 | 让 AI 一次性生成全部空目录和 `__init__.py` |
| 0.2 | 配置 pyproject.toml + 依赖 | pyproject.toml, uv.lock | 让 AI 列出所有依赖及版本 |
| 0.3 | 配置开发工具链 | mypy.ini, ruff.toml, .pre-commit-config.yaml | 让 AI 生成严格模式配置 |
| 0.4 | 编写 Docker Compose | docker-compose.yml (PostgreSQL 16 + Redis 7) | 让 AI 生成并注释每个配置 |
| 0.5 | 配置 SQLAlchemy + Alembic | alembic.ini, database.py, env.py | 让 AI 配置异步引擎 |
| 0.6 | 编写数据库迁移 | alembic/versions/001_initial.py (所有核心表) | 参考架构文档 8.2 节 |
| 0.7 | 配置 Pydantic Settings | config/settings.py (.env 驱动) | 数据库、Redis、JWT 密钥等 |
| 0.8 | 编写 Makefile + setup.sh | Makefile | `make dev`, `make test`, `make migrate` |
| 0.9 | 配置 CI 基础 | .github/workflows/ci.yml | lint + type-check + test |

**验收标准**: `docker-compose up -d && make migrate && make dev` 能启动 FastAPI（Swagger 可访问）。

---

#### 模块 1：pm_common 公共模块（第 1–2 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 1.1 | 统一响应封装 | `response.py`: `ApiResponse[T]` (code, message, data, timestamp) |
| 1.2 | 统一错误码和异常 | `errors.py`: `ErrorCode` 枚举, `BusinessError`, `NotFoundError` |
| 1.3 | FastAPI 全局异常处理 | `error_handler.py`: 捕获异常 → ApiResponse |
| 1.4 | Snowflake ID 生成器 | `id_generator.py`: 分布式唯一 ID |
| 1.5 | Decimal 工具 | `decimal_utils.py`: 精度控制、比较、格式化 |
| 1.6 | Redis 客户端封装 | `redis_client.py`: 连接池、分布式锁、Lua 脚本执行 |
| 1.7 | 数据库会话管理 | `database.py`: async_session_maker, get_db dependency |
| 1.8 | 单元测试 | 每个工具的测试 |

**关键代码示例：**

```python
# pm_common/response.py
from pydantic import BaseModel
from typing import Generic, TypeVar
T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None
    timestamp: int  # unix ms
```

```python
# pm_common/redis_client.py — 分布式锁
class RedisLock:
    async def acquire(self, key: str, ttl: int = 10) -> bool: ...
    async def release(self, key: str) -> None: ...

# Lua 脚本：原子冻结余额
FREEZE_BALANCE_LUA = """
local available = tonumber(redis.call('HGET', KEYS[1], 'available'))
local amount = tonumber(ARGV[1])
if available >= amount then
    redis.call('HINCRBYFLOAT', KEYS[1], 'available', -amount)
    redis.call('HINCRBYFLOAT', KEYS[1], 'frozen', amount)
    return 1
else
    return 0
end
"""
```

**验收标准**: `pytest tests/unit/test_common.py` 全部通过；`mypy src/pm_common/` 零错误。

---

#### 模块 2：pm_account 账户模块（第 2–3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 2.1 文档 | 账户接口设计 | docs/account-design.md |
| 2.2 领域模型 | Account, Position, LedgerEntry dataclass | domain/models.py |
| 2.3 枚举 | AccountStatus, EntryType | domain/enums.py |
| 2.4 领域事件 | BalanceFrozen, BalanceReleased, PositionUpdated | domain/events.py |
| 2.5 仓储接口 | AccountRepository (Protocol) | domain/repository.py |
| 2.6 核心逻辑 | AccountDomainService: | domain/service.py |
| | ① deposit() — 充值 | |
| | ② withdraw() — 提现 | |
| | ③ freeze_balance() — 冻结 | |
| | ④ release_balance() — 解冻 | |
| | ⑤ transfer() — 划转（清算用） | |
| | ⑥ update_position() — 持仓更新 | |
| 2.7 数据库 | accounts, positions, ledger_entries 表 ORM | infrastructure/db_models.py |
| 2.8 持久化 | SQLAlchemy 实现 AccountRepository | infrastructure/persistence.py |
| 2.9 Redis 缓存 | 余额快速查询 + Lua 原子冻结 | infrastructure/cache.py |
| 2.10 应用层 | AccountAppService + Pydantic Schemas | application/ |
| 2.11 REST API | POST /deposit, POST /withdraw, GET /balance, GET /positions | api/router.py |
| 2.12 单元测试 | 冻结/解冻、乐观锁、余额不足边界 | tests/unit/test_account_domain.py |
| 2.13 集成测试 | DB + Redis + API 完整流程 | tests/integration/test_account_api.py |

**关键设计决策：**
- `Account.version` 字段 + SQLAlchemy `with_for_update()` 实现乐观锁
- `LedgerEntry` Append-Only，永不 UPDATE/DELETE
- 所有金额用 `Decimal`，精度 4 位小数
- Redis Lua 脚本实现原子冻结（先查 available，够则扣减并增加 frozen）

**验收标准**: API 充值 → 查余额 → 冻结 → 解冻 → 查流水，全流程跑通。

---

#### 模块 3：pm_market 市场配置（第 3 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 3.1 | Market 领域模型 | domain/models.py: Market(id, title, description, status, min_price, max_price, tick_size, ...) |
| 3.2 | 市场状态枚举 | domain/enums.py: MarketStatus (ACTIVE, SUSPENDED, RESOLVED, SETTLED) |
| 3.3 | 静态配置文件 | config/markets.json: 预设 3-5 个示例市场 |
| 3.4 | MarketConfigService | 启动时加载 JSON + 内存缓存 | application/service.py |
| 3.5 | Pydantic Schemas | MarketResponse, MarketListResponse | application/schemas.py |
| 3.6 | REST API | GET /markets, GET /markets/{id} | api/router.py |
| 3.7 | 测试 | 配置加载 + API 查询 | tests/ |

**markets.json 示例：**
```json
[
  {
    "id": "MKT-BTC-100K-2026",
    "title": "Will BTC reach $100K by end of 2026?",
    "description": "Resolves YES if Bitcoin...",
    "status": "ACTIVE",
    "contract_types": ["YES", "NO"],
    "min_price": "0.01",
    "max_price": "0.99",
    "tick_size": "0.01",
    "max_position_per_user": 25000,
    "maker_fee_rate": "0.0001",
    "taker_fee_rate": "0.0002",
    "resolution_date": "2026-12-31T23:59:59Z"
  }
]
```

**验收标准**: 启动后 GET /markets 返回预配置市场列表。

---

#### 模块 4：pm_order 订单模块（第 3–4 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.1 文档 | 订单状态机 + API 设计 | docs/order-design.md |
| 4.2 枚举 | OrderSide (BUY/SELL), OrderType (LIMIT), OrderStatus, TimeInForce (GTC/IOC) | domain/enums.py |
| 4.3 领域模型 | Order (含状态机方法: accept, partially_fill, fill, cancel) | domain/models.py |
| 4.4 状态机 | 严格状态流转规则 | domain/models.py 内嵌 |

```
NEW → PENDING_RISK → OPEN → PARTIALLY_FILLED → FILLED
                  ↘              ↘            ↗
                   → REJECTED     → CANCELLED
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 4.5 | 领域事件 | domain/events.py: OrderPlaced, OrderCancelled, OrderFilled |
| 4.6 | 仓储接口 | domain/repository.py: OrderRepository (Protocol) |
| 4.7 | 核心逻辑 | domain/service.py: 下单校验、幂等 (client_order_id) |
| 4.8 | 数据库 ORM | infrastructure/db_models.py: OrderModel |
| 4.9 | 持久化实现 | infrastructure/persistence.py |
| 4.10 | 应用层 | application/: PlaceOrderCmd, CancelOrderCmd, OrderAppService |
| 4.11 | Schemas | application/schemas.py: PlaceOrderReq, OrderResp |
| 4.12 | REST API | POST /orders, DELETE /orders/{id}, GET /orders, GET /orders/{id} |
| 4.13 | 单元测试 | 状态机流转 (合法 + 非法)、幂等、价格校验 |
| 4.14 | 集成测试 | 下单 → 入库 → 查询 |

**关键设计决策：**
- `client_order_id` UNIQUE 约束实现幂等
- 价格校验：`Decimal("0.01") <= price <= Decimal("0.99")`
- 状态机：非法转换抛 `InvalidStateTransitionError`

**验收标准**: 能创建订单 → 查询 → 取消；重复 client_order_id 返回已存在订单。

---

#### 模块 5：pm_risk 风控模块（第 4–5 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 5.1 文档 | 风控规则定义文档 | docs/risk-rules.md |
| 5.2 | RiskCheckResult 模型 | domain/models.py: RiskCheckResult(passed, failed_rule, message) |
| 5.3 | 风控规则接口 (Protocol) | domain/rules.py |

```python
class RiskRule(Protocol):
    """每条风控规则的接口"""
    name: str
    async def check(self, order: Order, context: RiskContext) -> RiskCheckResult: ...
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 5.4 | 规则实现 | rules/balance_check.py: 余额 ≥ price × quantity |
| 5.5 | 规则实现 | rules/order_limit.py: 单笔 ≤ $10,000 |
| 5.6 | 规则实现 | rules/position_limit.py: 单市场 ≤ $25,000 |
| 5.7 | 规则实现 | rules/market_status.py: 市场必须 ACTIVE |
| 5.8 | 规则实现 | rules/price_range.py: 0.01 ≤ price ≤ 0.99 |
| 5.9 | 规则链 | domain/service.py: RiskDomainService (链式执行所有规则) |
| 5.10 | 应用层 | application/service.py: RiskCheckService (联动 Account 查余额/冻结) |
| 5.11 | 单元测试 | 每条规则的 pass/reject 测试 |
| 5.12 | 集成测试 | 下单 → 风控 → 余额冻结 |

**关键设计决策：**
- 规则链 (Chain of Responsibility)：按顺序执行，第一个失败即返回
- 规则可配置优先级和开关（MVP 硬编码，中期可从配置中心读取）
- 风控通过后**同步调用** Account 冻结余额

**验收标准**: 余额不足 → 拒绝；超限额 → 拒绝；价格超范围 → 拒绝；正常 → 通过并冻结。

---

#### 模块 6：pm_matching 撮合引擎（第 5–7 周）⭐ 核心难点

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.1 文档 | 撮合引擎设计 (LOB 数据结构 + 算法) | docs/matching-engine-design.md |
| 6.2 | OrderBook 模型 | engine/order_book.py |

**Python 订单簿核心数据结构：**

```python
from sortedcontainers import SortedDict
from collections import deque
from decimal import Decimal

class OrderBook:
    def __init__(self, market_id: str):
        self.market_id = market_id
        # 买方: 价格从高到低 (neg key trick)
        self._bids: SortedDict = SortedDict()  # {neg_price: deque[Order]}
        # 卖方: 价格从低到高
        self._asks: SortedDict = SortedDict()  # {price: deque[Order]}

    def add_order(self, order: Order) -> list[Trade]:
        """添加订单，返回撮合产生的成交列表"""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """取消订单，从订单簿中移除"""
        ...

    def get_best_bid(self) -> Decimal | None: ...
    def get_best_ask(self) -> Decimal | None: ...
    def get_depth(self, levels: int = 10) -> dict: ...
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.3 | 撮合算法 | engine/matching_algo.py: match_limit_order() |
| 6.4 | 市场路由 | engine/market_router.py: Dict[str, OrderBook] |
| 6.5 | 引擎主循环 | engine/engine.py: asyncio.Queue 接收订单 → 撮合 → 输出成交 |
| 6.6 | MatchResult 模型 | domain/models.py: Trade, MatchResult |
| 6.7 | 应用层 | application/service.py: MatchingEngineService |
| 6.8 | API | api/router.py: GET /orderbook/{market_id} (订单簿深度) |
| 6.9 | 单元测试 (10+ 场景) | tests/unit/test_matching_engine.py: |

**撮合测试场景清单：**

| # | 场景 | 预期结果 |
|---|------|----------|
| 1 | 完全匹配: BUY 100@0.60 vs SELL 100@0.60 | 成交 100@0.60 |
| 2 | 价格交叉: BUY@0.65 vs SELL@0.60 | 以 maker 价 0.60 成交 |
| 3 | 部分成交: BUY 100@0.60 vs SELL 50@0.60 | 成交 50, 买单剩 50 挂单 |
| 4 | Taker 吃多笔: BUY 200@0.65 vs [SELL 50@0.60, SELL 80@0.62, SELL 100@0.65] | 3 笔成交 |
| 5 | IOC 未完全成交 | 成交部分，剩余自动取消 |
| 6 | 空簿下单 | 直接挂入订单簿 |
| 7 | 取消订单 | 从订单簿移除 |
| 8 | 订单簿深度 | 按价格档位聚合数量 |
| 9 | 同价格时间优先 | 先到的订单先成交 |
| 10 | 价格不交叉 | 无成交，双方挂单 |
| 11 | YES/NO 独立订单簿 | 互不干扰 |
| 12 | 边界价格 0.01/0.99 | 正常撮合 |

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 6.10 | 集成测试 | 提交订单 → 撮合 → 返回 Trade |
| 6.11 | 性能测试 | 基准测试 (目标: 1k–5k ops/sec) |

**关键设计决策：**
- `SortedDict` (基于 B-tree) 替代 Java `TreeMap`，O(log n) 插入/查找
- `deque` 替代 Java `LinkedList`，FIFO 时间优先
- 单线程处理（asyncio.Queue 作为入口），无并发问题
- MVP 不做合成撮合，YES/NO 各自独立 OrderBook
- 撮合引擎是纯内存操作，不直接访问数据库

**验收标准**: 12 个测试场景全部通过；性能基准 >1k ops/sec。

---

#### 模块 7：pm_clearing 清算模块（第 7–8 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.1 文档 | 清算流程设计 | docs/clearing-design.md |
| 7.2 | Trade, Settlement 模型 | domain/models.py |
| 7.3 | 数据库 ORM | infrastructure/db_models.py: TradeModel |
| 7.4 | 清算核心逻辑 | domain/service.py: ClearingDomainService |

**清算流程（单笔成交）：**
```
1. 记录成交 (INSERT trades)
2. 计算手续费 (maker: 0.01%, taker: 0.02%)
3. 买方：解冻 → 扣款(price × qty + fee) → 增加持仓
4. 卖方：解冻 → 扣款(qty 的持仓) → 入账((1-price) × qty - fee) [或更新持仓]
5. 写入资金流水 (INSERT ledger_entries × N)
6. 所有操作在同一个数据库事务中
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 7.5 | 事务保证 | async with session.begin() 包裹全部操作 |
| 7.6 | 应用层 | application/service.py: ClearingAppService |
| 7.7 | REST API | GET /trades (成交查询) |
| 7.8 | 单元测试 | 费用计算、余额变化验证 |
| 7.9 | 集成测试 | 成交 → 清算 → 余额 + 持仓 + 流水 全部正确 |

**关键设计决策：**
- MVP 同步清算：撮合产生 Trade → 立即调用 ClearingService
- 数据库事务级别：SERIALIZABLE（确保资金安全）
- 零和验证：所有用户 available + frozen 总和 = 系统总充值额

**验收标准**: 撮合后清算正确；买卖双方余额变化符合预期；流水记录完整。

---

#### 模块 8：pm_gateway 网关/认证（第 8–9 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 8.1 文档 | API 总览 + 鉴权方案 | docs/api-overview.md |
| 8.2 | User 模型 + ORM | user/models.py, user/db_models.py |
| 8.3 | 密码哈希 (bcrypt) | auth/password.py |
| 8.4 | JWT 生成/验证 | auth/jwt_handler.py: create_token, verify_token |
| 8.5 | FastAPI 依赖注入 | auth/dependencies.py: get_current_user |
| 8.6 | 用户注册/登录 | user/service.py + api/router.py |
| 8.7 | 限流中间件 | middleware/rate_limit.py: 令牌桶算法 |
| 8.8 | 请求日志中间件 | middleware/request_log.py |
| 8.9 | 全局异常处理 | middleware/error_handler.py |
| 8.10 | 所有 Router 加认证 | 给 /orders, /accounts 等路由添加 `Depends(get_current_user)` |
| 8.11 | 单元测试 | JWT 生成/验证、密码哈希 |
| 8.12 | 集成测试 | 注册 → 登录 → Token → 访问受保护 API |

**关键代码示例：**

```python
# auth/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(
    credentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = verify_token(credentials.credentials)
    user = await user_repo.get_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

**验收标准**: 未登录 → 401；登录 → Token → 能访问所有交易 API。

---

#### 模块 9：端到端集成（第 9–10 周）

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.1 | 完整交易链路集成 | 在 main.py 中串联所有模块 |
| 9.2 | E2E 测试 | tests/e2e/test_full_trading_flow.py: |

**E2E 完整流程：**
```
1. POST /auth/register  → 注册用户 A, B
2. POST /auth/login     → 获取 Token
3. POST /accounts/deposit → A 充值 $10,000
4. POST /accounts/deposit → B 充值 $10,000
5. GET  /markets         → 查看可用市场
6. POST /orders          → A 买入 YES 100@0.60 (冻结 $6,000)
7. POST /orders          → B 卖出 YES 100@0.55 (挂单)
8. POST /orders          → A 买入 YES 100@0.55 → 与 B 撮合
9. GET  /accounts/balance → 验证 A: 余额减少, 持仓增加
10. GET /accounts/balance → 验证 B: 余额增加 (或持仓减少)
11. GET /trades           → 查看成交记录
12. GET /accounts/ledger  → 查看资金流水
13. 零和验证: A.total + B.total == $20,000
```

| 步骤 | 具体任务 | 产出物 |
|------|----------|--------|
| 9.3 | 异常场景测试 | 余额不足、重复下单、取消已成交、超限额 |
| 9.4 | 零和验证脚本 | scripts/verify_consistency.py |
| 9.5 | Docker 打包 | Dockerfile (多阶段构建) |
| 9.6 | 完整 Docker Compose | docker-compose.full.yml |
| 9.7 | Seed 数据脚本 | scripts/seed_data.py (预置市场 + 测试用户) |
| 9.8 | API 文档完善 | FastAPI 自动生成的 Swagger 已足够 |

**验收标准**: `docker-compose -f docker-compose.full.yml up` → `pytest tests/e2e/ -v` 全部通过 → 零和验证通过。

---

### 2.6 MVP 关键里程碑

```
Week 1:   [脚手架 + pm_common] ── 项目结构、Docker、数据库、公共工具就绪
Week 2-3: [pm_account] ────────── 充值/余额/冻结/流水 可用
Week 3:   [pm_market] ─────────── 市场配置 可用
Week 4:   [pm_order] ──────────── 下单/查单/取消 可用
Week 5:   [pm_risk] ───────────── 风控检查 可用
Week 6-7: [pm_matching] ──────── 撮合引擎 可用 ⭐
Week 8:   [pm_clearing] ────────── 清算结算 可用
Week 9:   [pm_gateway] ─────────── 认证 + 限流 可用
Week 10:  [E2E + 发布] ─────────── MVP 发布 🎉
```

---

## 三、Phase 2 — 中期实施计划

### 3.1 核心目标
将 Python 单体拆分为独立微服务，引入 Kafka 事件驱动，新增市场管理/行情/预言机/通知服务。

### 3.2 中期模块实施顺序

| 优先级 | 模块 | 关键变更 | 预计周期 |
|--------|------|----------|----------|
| **P0** | 基础设施升级 | Kafka (Redpanda) + Consul | 2 周 |
| **P0** | 微服务拆分 | 每个 pm_* 模块 → 独立 FastAPI 应用 | 3 周 |
| **P1** | pm-market-service | 市场生命周期状态机 + CRUD | 2 周 |
| **P1** | pm-oracle-service | 数据采集 + 人工裁决 + 结算触发 | 2 周 |
| **P2** | pm-market-data-service | TimescaleDB K线 + WebSocket 推送 | 2 周 |
| **P2** | pm-notification-service | Kafka 消费 + WebSocket 通知 | 2 周 |
| **P3** | API Gateway | Kong 或 Traefik 替换内嵌路由 | 1 周 |
| **P3** | 监控体系 | Prometheus + Grafana + 链路追踪 | 2 周 |

### 3.3 微服务拆分策略

每个模块拆分为独立 FastAPI 应用，通过 HTTP/gRPC 通信：

```
MVP (单进程)                        中期 (多服务)
─────────────                       ──────────────
pm_account.service.freeze()    →    POST http://pm-account:8001/internal/freeze
pm_risk.service.check()        →    POST http://pm-risk:8002/internal/check
pm_matching.service.submit()   →    Kafka topic: orders.commands
pm_clearing.service.settle()   →    Kafka topic: trades.events → consumer
```

### 3.4 性能关键模块替换评估

| 模块 | Python 性能 | 是否需要重写 | 推荐时机 |
|------|------------|-------------|----------|
| pm_matching | 1k–5k ops/sec | 如需 >10k：用 Cython/Rust 重写核心算法 | Phase 3 |
| pm_account | 足够 (IO bound) | 通常不需要 | — |
| pm_risk | 足够 | 规则引擎复杂后考虑 Java | Phase 3 |
| pm_clearing | 足够 (IO bound) | 通常不需要 | — |

---

## 四、Phase 3 — 生产就绪计划

### 4.1 核心升级

| 优先级 | 模块 | 关键升级 | 语言 |
|--------|------|----------|------|
| **P0** | 撮合引擎重写 | Java + LMAX Disruptor 或 Rust | Java/Rust |
| **P0** | 数据库高可用 | PostgreSQL 主从 + 连接池 | Infra |
| **P0** | K8s 部署 | 多副本 + 自动故障转移 | Infra |
| **P1** | 合成撮合 | YES+NO 对冲撮合逻辑 | Java/Rust |
| **P1** | 智能风控 | 规则引擎 (Python rule-engine 或 Java Drools) | Python/Java |
| **P1** | 自动裁决 | Temporal 工作流 (Python SDK) | Python |
| **P2** | 分析系统 | ClickHouse + Pandas/Polars | Python |
| **P2** | 审计合规 | 不可篡改日志 | Python/Java |

---

## 五、每个模块通用的 Python 实施模板

```
┌──────────────────────────────────────────────────────────────┐
│               Python 模块实施标准流程                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 📋 需求与设计                                             │
│     ├── 编写模块设计文档 (接口、数据模型、流程图)                │
│     ├── 定义 Pydantic Schema (请求/响应)                      │
│     └── 设计数据库表 (Alembic migration)                      │
│                                                              │
│  2. 🏗️ 领域层 (domain/)                                      │
│     ├── models.py — dataclass/Pydantic 领域模型               │
│     ├── enums.py — 状态/类型枚举                              │
│     ├── events.py — 领域事件                                  │
│     ├── service.py — 核心业务逻辑 (纯 Python, 无 IO)          │
│     └── repository.py — Protocol 仓储接口                     │
│                                                              │
│  3. 🔧 基础设施层 (infrastructure/)                            │
│     ├── db_models.py — SQLAlchemy ORM 模型                    │
│     ├── persistence.py — 仓储接口的 SQLAlchemy 实现            │
│     └── cache.py — Redis 缓存实现                             │
│                                                              │
│  4. 🖥️ 应用层 (application/)                                  │
│     ├── schemas.py — Pydantic 请求/响应 Schema                │
│     ├── commands.py — 命令对象 (可选)                          │
│     └── service.py — 用例编排 (调用 domain + infrastructure)   │
│                                                              │
│  5. 🌐 API 层 (api/)                                         │
│     └── router.py — FastAPI APIRouter                         │
│                                                              │
│  6. ✅ 测试                                                   │
│     ├── tests/unit/test_xxx_domain.py — 领域逻辑测试          │
│     ├── tests/integration/test_xxx_api.py — API + DB 测试     │
│     └── 覆盖率目标 ≥ 80%                                     │
│                                                              │
│  7. 🔍 质量检查                                               │
│     ├── mypy src/pm_xxx/ --strict     (类型检查)              │
│     ├── ruff check src/pm_xxx/        (Lint)                  │
│     └── pytest --cov=src/pm_xxx       (覆盖率)                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、AI Vibe Coding 使用建议 (Python 版)

### 6.1 推荐工作流

```
每个模块的 AI 辅助流程：

1. "帮我设计 pm_account 模块的 API 接口和数据模型"
   → AI 生成设计文档 → 你 Review

2. "根据这个设计，生成 domain/ 下的所有文件"
   → AI 生成 models.py, enums.py, service.py, repository.py
   → 你检查业务逻辑是否正确

3. "生成 SQLAlchemy ORM 模型和 Alembic 迁移"
   → AI 生成 db_models.py + migration
   → 你检查字段类型和约束

4. "生成 FastAPI Router 和 Pydantic Schemas"
   → AI 生成完整 CRUD API
   → 你检查验证规则

5. "为 AccountDomainService 生成全面的单元测试"
   → AI 生成 pytest 测试
   → 你补充边界条件

6. "运行测试并修复问题"
   → AI 分析错误日志，修复 Bug

7. "对 pm_account 模块做 Code Review"
   → AI 检查潜在问题
```

### 6.2 Python 特别注意事项

| 事项 | 说明 |
|------|------|
| **所有金额用 `Decimal`** | 禁止 `float`，数据库也用 `DECIMAL`/`NUMERIC` |
| **async 一路到底** | FastAPI → Service → Repository → asyncpg，不要混用 sync |
| **类型标注完整** | 所有函数参数和返回值都要标注类型，mypy strict |
| **Pydantic v2** | 用 `model_validator` 替代 v1 的 `validator` |
| **测试隔离** | 每个测试用独立的数据库事务 + rollback |

---

## 七、风险与应对 (Python 特有)

| 风险 | 影响 | 应对 |
|------|------|------|
| 撮合性能瓶颈 | Python 纯计算慢 | ① MVP 够用；② 热路径可用 Cython 加速；③ Phase 3 用 Rust/Java 重写 |
| GIL 限制 | CPU 密集任务无法并行 | 撮合本就是单线程设计；IO 操作用 asyncio |
| 类型安全弱于 Java | 运行时才发现错误 | mypy strict + Pydantic 验证 + 完善测试 |
| 依赖管理混乱 | 版本冲突 | 用 uv/Poetry 锁定；Docker 隔离环境 |
| 异步代码复杂度 | Debug 困难 | 用 structlog 结构化日志；学习 asyncio 异常处理 |

---

## 八、快速参考 — 一页纸行动清单

```
Phase 1 — Python MVP (8-12 周):
  □ Week 1:   项目脚手架 + Docker + Alembic + pm_common
  □ Week 2-3: pm_account 账户模块 (充值/冻结/流水)
  □ Week 3:   pm_market 市场配置 (静态 JSON)
  □ Week 4:   pm_order 订单模块 (下单/状态机/幂等)
  □ Week 5:   pm_risk 风控模块 (规则链)
  □ Week 6-7: pm_matching 撮合引擎 ⭐ (OrderBook + LOB)
  □ Week 8:   pm_clearing 清算模块 (资金划转/手续费)
  □ Week 9:   pm_gateway 认证模块 (JWT/限流)
  □ Week 10:  E2E 测试 + Docker 打包 + MVP 发布 🎉

Phase 2 — 微服务拆分 (10-16 周):
  □ Kafka + Consul 基础设施
  □ 单体 → 独立 FastAPI 微服务
  □ pm-market-service (市场生命周期)
  □ pm-oracle-service (数据采集 + 裁决)
  □ pm-market-data-service (K线 + WebSocket)
  □ pm-notification-service (通知)
  □ Kong/Traefik + Prometheus + Grafana 🎉

Phase 3 — 生产就绪 (12-20 周):
  □ 撮合引擎 Java/Rust 重写 (如需高性能)
  □ 数据库高可用 + K8s 部署
  □ 合成撮合 + 智能风控
  □ Temporal 自动裁决
  □ ClickHouse 分析 + 审计合规
  □ 安全加固 + 性能优化 + 正式发布 🚀
```

---

*文档版本: v2.0 (Python MVP) | 生成日期: 2026-02-20*
