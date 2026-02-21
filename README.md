# 预测市场平台 — DEV MVP

**Binary Prediction Market Platform — Single-Ledger Matching Engine**

> Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 · 单账本撮合架构

---

## 快速上手（30 秒）

```bash
cp .env.example .env
make up        # 启动 PG16 + Redis7
make migrate   # 运行所有 11 条迁移（建表 + 种子数据）
make dev       # 启动开发服务器 → http://localhost:8000
make test      # 运行测试
```

健康检查：`curl http://localhost:8000/health` → `{"status":"ok","version":"0.1.0"}`

Swagger UI：`http://localhost:8000/docs`

---

## 项目结构

```
DEV_MVP/
├── Planning/                          ← 所有设计和计划文档（必读）
│   ├── 预测市场平台_完整实施计划_v4_Python.md   ← 主计划 v4.1（总览 + 里程碑）
│   ├── Detail_Design/
│   │   ├── README.md                  ← 设计文档索引（从这里开始）
│   │   ├── 01_全局约定与数据库设计.md  v2.3  ← DB Schema + 枚举 + 不变量
│   │   ├── 02_API接口契约.md           v1.2  ← 20个接口 + 错误码 + 响应格式
│   │   ├── 03_撮合引擎与清算流程设计.md v1.2  ← 核心算法伪代码
│   │   └── 04_WAL预写日志与故障恢复设计.md v1.1 ← 熔断 + 恢复
│   ├── Implementation/
│   │   ├── 2026-02-20-scaffolding-design.md  ← 脚手架设计文档
│   │   └── 2026-02-20-scaffolding-plan.md    ← 脚手架实施计划（16个任务，已完成）
│   ├── archive/                       ← v1~v3 历史版本（仅供参考）
│   └── 参考资料_单账本撮合引擎设计方案_v1.md
│
├── src/
│   ├── main.py                        ← FastAPI 入口（uvloop + lifespan + AppError handler）
│   ├── pm_common/                     ← 共享工具层（Module 1，已完成）
│   │   ├── enums.py                   ← 全局枚举（与 DB CHECK 约束完全一致）
│   │   ├── errors.py                  ← AppError + 所有错误码（1xxx~9xxx）
│   │   ├── response.py                ← ApiResponse 统一响应封装
│   │   ├── cents.py                   ← 美分整数工具（validate_price / display / fee）
│   │   ├── id_generator.py            ← Snowflake ID 生成器
│   │   ├── datetime_utils.py          ← UTC 时间工具
│   │   ├── database.py                ← SQLAlchemy async engine + session factory
│   │   └── redis_client.py            ← Redis 连接（仅限流/会话，余额走 PG）
│   ├── pm_gateway/                    ← 认证模块（待实现）
│   ├── pm_account/                    ← 账户/持仓模块（待实现）
│   ├── pm_market/                     ← 话题模块（待实现）
│   ├── pm_order/                      ← 订单模块（待实现）
│   ├── pm_risk/                       ← 风控模块（待实现）
│   ├── pm_matching/                   ← 撮合引擎（待实现，最复杂）
│   └── pm_clearing/                   ← 清算模块（待实现）
│
├── config/
│   └── settings.py                    ← Pydantic Settings（读取 .env）
│
├── alembic/
│   ├── env.py                         ← Alembic async 配置
│   └── versions/
│       ├── 001_create_common_functions.py   ← fn_update_timestamp()
│       ├── 002_create_users.py
│       ├── 003_create_accounts.py
│       ├── 004_create_markets.py
│       ├── 005_create_orders.py             ← 含 partial index（活跃订单/自成交检查）
│       ├── 006_create_trades.py
│       ├── 007_create_positions.py
│       ├── 008_create_ledger_entries.py     ← BIGSERIAL，Append-Only
│       ├── 009_create_wal_events.py
│       ├── 010_create_circuit_breaker_events.py
│       └── 011_seed_initial_data.py         ← SYSTEM_RESERVE / PLATFORM_FEE / 3 个样本话题
│
├── tests/
│   ├── conftest.py                    ← AsyncClient fixture
│   ├── unit/                          ← 55 个单元测试（全通过）
│   └── integration/  e2e/             ← 待填充
│
├── docker-compose.yml                 ← postgres:16-alpine + redis:7-alpine
├── Dockerfile                         ← 两阶段构建（uv）
├── Makefile                           ← up / down / dev / test / migrate / lint / typecheck
├── pyproject.toml                     ← 依赖管理（uv）
├── ruff.toml                          ← Linter 配置
└── mypy.ini                           ← 严格类型检查
```

---

## 设计文档在哪里

| 问题 | 看哪个文档 |
|------|-----------|
| 整体里程碑、模块划分、工期估算 | `Planning/预测市场平台_完整实施计划_v4_Python.md` |
| 所有设计文档的索引和依赖关系 | `Planning/Detail_Design/README.md` ← **从这里开始** |
| 数据库表结构（DDL 权威来源） | `Planning/Detail_Design/01_全局约定与数据库设计.md` |
| API 接口定义（错误码、响应格式） | `Planning/Detail_Design/02_API接口契约.md` |
| 撮合算法、四种场景、清算伪代码 | `Planning/Detail_Design/03_撮合引擎与清算流程设计.md` |
| 熔断机制、故障恢复、运行时校验 | `Planning/Detail_Design/04_WAL预写日志与故障恢复设计.md` |

**推荐阅读顺序**：`01 → 03 → 02 → 04`

---

## 开发进度

### 整体里程碑（来自主计划 v4.1）

| 模块 | 描述 | 状态 |
|------|------|------|
| **Module 0** | 脚手架：Git / Docker / Alembic / 9张表 | ✅ 完成 |
| **Module 1** | pm_common：enums / errors / cents / ID / DB / Redis | ✅ 完成 |
| **Module 2** | pm_gateway：注册 / 登录 / JWT | 🔲 待开始 |
| **Module 3** | pm_account：充值 / 余额 / 流水 | 🔲 待开始 |
| **Module 4** | pm_market：话题列表 / 订单簿快照 | 🔲 待开始 |
| **Module 5** | pm_risk + pm_order：下单 / 风控 / 撮合入口 | 🔲 待开始 |
| **Module 6** | pm_matching：内存订单簿 + 撮合引擎 | 🔲 待开始 |
| **Module 7** | pm_clearing：四种场景清算 + Netting | 🔲 待开始 |
| **Module 8** | pm_order：持仓 / 成交记录查询 | 🔲 待开始 |
| **Module 9** | Admin：裁决 / 不变量验证 | 🔲 待开始 |

### 当前状态快照

```
测试：55 个单元测试通过（make test）
Lint：ruff 零报错（make lint）
类型：mypy 严格模式零报错（make typecheck）
数据库：11 条迁移全部可 downgrade → upgrade（全周期验证）
种子数据：SYSTEM_RESERVE / PLATFORM_FEE / 3 个样本市场
```

---

## 中断后如何继续开发（Pick Up Guide）

> 这个项目预计开发周期为数天到数周，以下步骤保证每次重新开始都能快速恢复状态。

### 第一步：确认环境正常（2 分钟）

```bash
make up                   # 启动 Docker（PG + Redis）
uv run alembic current    # 应显示 011 (head)
make test                 # 应全绿
make lint                 # 应零报错
```

如果测试失败，先不要继续写新代码，排查原因。

### 第二步：看 git log 确认在做什么

```bash
git log --oneline -10     # 最近10条提交，了解上次在哪停下
git status                # 是否有未提交的 WIP
git stash list            # 是否有 stash
```

### 第三步：找到下一个任务

1. 看 **`Planning/预测市场平台_完整实施计划_v4_Python.md`** 的里程碑章节，确认当前在哪个 Module
2. 找对应 Module 的实施计划文件：`Planning/Implementation/YYYY-MM-DD-<module-name>-plan.md`
   - 如果还没有：先用 `/brainstorm` 生成设计文档，再用 `/plan` 生成实施计划
3. 找到计划里第一个未完成的 Task，继续执行

### 第四步：开始新 Module 的标准流程

```
/brainstorm   → 确认设计（与 AI 对话，生成 design.md）
/plan         → 生成 Task 级实施计划（生成 plan.md）
              → 选择执行方式：
                a) 当前 session 执行（subagent-driven-development）
                b) 新开 session 执行（executing-plans）
```

### 告诉 AI 上下文的标准开场白

每次新 session 开始，把以下信息告诉 AI：

```
我们在开发一个二元预测市场平台（单账本撮合引擎架构）。
工作目录：/Users/pangpanghu007/Documents/Python_Project/predict_market/DEV_MVP
设计文档在 Planning/Detail_Design/（先读 README.md）
主计划在 Planning/预测市场平台_完整实施计划_v4_Python.md
当前完成到 Module 1（脚手架 + pm_common），下一步是 Module 2（pm_gateway 认证模块）。
上次实施计划：Planning/Implementation/2026-02-20-scaffolding-plan.md
```

---

## 核心架构约定（开发时必知）

### 1. 全局整数化 — 禁止 float/Decimal

所有价格、金额、余额统一用 `int`（单位：美分）。

```python
# 正确
price: int = 65           # 65 美分 = $0.65
amount: int = 6500        # $65.00
fee = calculate_fee(amount, fee_bps)   # src/pm_common/cents.py

# 错误
price: float = 0.65       # ❌ 禁止
```

### 2. 单账本 — 单一 YES 订单簿

每个 market 只有一个 YES 订单簿。NO 操作通过转换层映射：

| 用户操作 | book_type | 冻结物 |
|---------|-----------|--------|
| Buy YES @ P | NATIVE_BUY | 资金 P×qty |
| Sell YES @ P | NATIVE_SELL | YES 持仓 qty |
| Buy NO @ P | SYNTHETIC_SELL（转换为 Sell YES @ 100-P） | 资金 P×qty |
| Sell NO @ P | SYNTHETIC_BUY（转换为 Buy YES @ 100-P） | NO 持仓 qty |

### 3. 四种撮合场景

```
NATIVE_BUY  + NATIVE_SELL   → TRANSFER_YES（YES 持仓转手）
NATIVE_BUY  + SYNTHETIC_SELL → MINT（铸造合约对，Reserve +100/份）
SYNTHETIC_BUY + NATIVE_SELL  → BURN（销毁合约对，Reserve -100/份）
SYNTHETIC_BUY + SYNTHETIC_SELL → TRANSFER_NO（NO 持仓转手）
```

详见：`Planning/Detail_Design/03_撮合引擎与清算流程设计.md`

### 4. 5 条核心不变量

任何改动都不得破坏这 5 条，详见 `01_全局约定与数据库设计.md §5`：

1. **份数平衡**：`total_yes_shares = total_no_shares`（DB CHECK 约束保证）
2. **托管一致**：`reserve_balance = total_yes_shares × 100`（DB CHECK 约束保证）
3. **成本守恒**：`reserve_balance + pnl_pool = Σ(用户 cost_sum)`
4. **全局零和**：`Σ(所有用户资金) + SYSTEM_RESERVE + PLATFORM_FEE = 常数`
5. **Reserve 对账**：`SYSTEM_RESERVE.available_balance = Σ(活跃话题 reserve_balance)`

### 5. 并发模型 — Per-Market Lock

```python
# 每个 market_id 一把 asyncio.Lock
# 整条链路串行化：转换 → 风控 → 撮合 → 清算 → Netting
async with market_locks[market_id]:
    ...
```

---

## 常用命令

```bash
make up           # 启动 Docker 容器
make down         # 停止 Docker 容器
make dev          # 启动开发服务器（热重载）
make test         # 运行所有测试
make lint         # ruff 检查
make format       # ruff 格式化
make typecheck    # mypy 严格检查
make migrate      # alembic upgrade head
make migration MSG="describe change"  # 生成新迁移
```

---

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 语言 | Python | 3.12+ |
| 包管理 | uv | latest |
| Web 框架 | FastAPI | ≥0.109 |
| 事件循环 | uvloop | ≥0.19 |
| ORM | SQLAlchemy async | 2.0 |
| DB 驱动 | asyncpg | ≥0.29 |
| 数据库 | PostgreSQL | 16 |
| 缓存/限流 | Redis | 7 |
| 迁移 | Alembic | ≥1.13 |
| 数据校验 | Pydantic v2 | ≥2.5 |
| 认证 | python-jose (JWT) | ≥3.3 |
| 密码哈希 | passlib[bcrypt] | ≥1.7 |
| 测试 | pytest + pytest-asyncio | ≥8.0 |
| HTTP 测试 | httpx | ≥0.26 |
| Lint | ruff | ≥0.2 |
| 类型检查 | mypy strict | ≥1.8 |

---

*最后更新: 2026-02-20 — Module 0 + Module 1 完成*
