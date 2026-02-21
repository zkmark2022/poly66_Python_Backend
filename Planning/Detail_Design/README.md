# 预测市场平台 — 详细设计文档索引

> **项目**: 二元预测市场平台 (Binary Prediction Market)
> **架构**: 单账本撮合引擎 (Single-Ledger Matching Engine)
> **技术栈**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 async / asyncpg / PostgreSQL 16
> **上游文档**: `../预测市场平台_完整实施计划_v4_Python.md`
> **最后更新**: 2026-02-20

---

## 文档总览

```
Detail_Design/
├── README.md                              ← 本文件
├── 01_全局约定与数据库设计.md       v2.3    基石层: 所有模块的公共约定和数据库 Schema
├── 02_API接口契约.md                v1.2    契约层: 前后端对接的唯一依据
├── 03_撮合引擎与清算流程设计.md     v1.2    核心层: 撮合算法 + 清算资金流转
└── 04_WAL预写日志与故障恢复设计.md  v1.1    防护层: 崩溃恢复 + 熔断 + 运行时校验
```

---

## 各文档职责

### 01 — 全局约定与数据库设计 (v2.3)

**定位**: 整个项目的基石，所有模块开发时必须参考。

**核心内容**:
- 全局整数化规则（美分制，禁止 float/Decimal）
- 主键策略、时间字段、枚举约定、外键策略、软删除策略、并发控制约定
- 9 张数据库表完整 DDL: `users`, `accounts`, `markets`, `orders`, `trades`, `positions`, `ledger_entries`, `wal_events`, `circuit_breaker_events`
- 5 条核心不变量（份数平衡、托管平衡、成本守恒、全局零和、Reserve 一致性）及验证 SQL
- Python 枚举定义、SQLAlchemy ORM 映射指南、Alembic 迁移规范

**关键设计决策**:
- `cost_sum` 替代 `avg_cost`（避免整数除法精度丢失）
- MVP 不使用数据库级外键（为微服务拆分预留）
- Redis 仅用于限流/会话，余额操作纯走 PostgreSQL

---

### 02 — API 接口契约 (v1.2)

**定位**: 前后端对接与集成测试的唯一依据。

**核心内容**:
- 20 个 REST API 接口的完整定义（路径、请求/响应 JSON、错误码）
- 全局约定: JWT 认证、统一响应封装、金额双字段策略（`_cents` + `_display`）
- 游标分页规范（基于主键 `id`，不用 `created_at`）
- 错误码体系（1xxx~9xxx 按模块划分）
- 限流规则、HTTP 状态码映射
- `frozen_amount` 前端展示规范
- Pydantic v2 Schema 示例

**接口模块划分**:
| 模块 | 接口数 | 关键接口 |
|------|--------|---------|
| pm_gateway (认证) | 3 | register, login, refresh |
| pm_account (账户) | 4 | balance, deposit, withdraw, ledger |
| pm_market (话题) | 3 | markets list/detail, orderbook |
| pm_order (订单) | 4 | **下单(核心)**, cancel, list, detail |
| pm_account (持仓) | 2 | positions list/detail |
| pm_clearing (成交) | 1 | trades list |
| admin (管理) | 3 | verify-invariants, stats, **resolve** |

---

### 03 — 撮合引擎与清算流程设计 (v1.2)

**定位**: 平台的核心业务逻辑，从下单到清算的完整算法。

**核心内容**:
- 单一 YES 订单簿架构（NO 操作通过转换层映射）
- O(1) 内存订单簿: 固定数组 `[100]` + `_best_bid`/`_best_ask` 游标
- 四种撮合场景判定与执行: MINT / TRANSFER_YES / TRANSFER_NO / BURN
- 完整清算流程伪代码: 余额划转 → 持仓更新 → 手续费 → 流水 → 退款 → Reserve/pnl_pool
- Auto-Netting 自动抵消机制
- `_sync_frozen_amount` 覆盖赋值算法（非减法）
- 双侧退款 `refund_price_improvement_and_fee_surplus`（Maker + Taker）
- SYSTEM_RESERVE 延迟聚合（核心事务只 INSERT，后台聚合）

**关键数据流**:
```
用户下单 → 转换层(NO→YES映射) → 风控+冻结 → 撮合(内存OrderBook)
  → 清算(4场景) → Netting → 入簿/完结 → WAL审计
```

---

### 04 — 故障恢复与运行时防护设计 (v1.1)

**定位**: 保障系统在异常情况下的数据一致性和可用性。

**核心内容**:
- DB 全量重建: 唯一恢复路径，PostgreSQL `orders` 表就是实时快照
- 事务回滚内存保护: Evict + Lazy Rebuild（DB 回滚时销毁内存 OrderBook）
- WAL 审计日志: 5 种事件类型，仅用于事后排查，不参与恢复
- 熔断机制: 8 种触发条件 → HALT + 告警，不自动回滚
- 三层运行时校验: 逐笔(轻量) → 事务后(中量) → 定时巡检(全量)
- 监控指标与告警配置

**核心洞察**:
> 在同步 DB 事务架构下，PostgreSQL 从不撒谎。不需要快照，不需要 WAL 重放。

---

## 文档依赖关系

```
                    ┌─────────────────────────┐
                    │  上游: 完整实施计划 v4.1  │
                    │  (项目范围/里程碑/技术栈) │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  01 全局约定与数据库设计  │
                    │  v2.3                    │
                    │  ─────────────────────── │
                    │  DB Schema / 枚举 / 约定 │
                    │  ⭐ 所有文档的基石        │
                    └──┬────────────┬─────────┘
                       │            │
          ┌────────────▼──┐   ┌────▼──────────────┐
          │ 02 API 接口契约│   │ 03 撮合引擎与清算  │
          │ v1.2           │   │ v1.2              │
          │ ────────────── │   │ ──────────────── │
          │ REST API 定义  │   │ 核心算法伪代码    │
          │ 前后端契约     │◄──│ 撮合+清算+Netting │
          └────────────────┘   └────────┬─────────┘
                                        │
                              ┌─────────▼─────────┐
                              │ 04 故障恢复与防护   │
                              │ v1.1               │
                              │ ─────────────────  │
                              │ 恢复/熔断/校验/监控│
                              └────────────────────┘
```

**读取顺序建议**: 01 → 03 → 02 → 04

- 先读 01 建立全局概念（美分制、单账本、四种场景）
- 再读 03 理解核心算法（这是最复杂的文档）
- 然后读 02 了解 API 如何暴露这些能力
- 最后读 04 了解异常防护

---

## 跨文档关键引用索引

| 概念 | 定义位置 | 引用位置 |
|------|---------|---------|
| 四种撮合场景 (MINT/TRANSFER/BURN) | 01 §2.5, 03 §6 | 02 §7.1, 04 §4.2 |
| 5 条核心不变量 | 01 §5 | 03 §11, 04 §6, 02 §8.1 |
| per-market asyncio.Lock | 01 §1.7 | 03 §2.1, 04 §3.2 |
| frozen_amount 冻结机制 | 01 §2.4 | 03 §4/§5.1/§7.3, 02 §5.1 |
| cost_sum 累计成本 | 01 §1.1/§2.6 | 03 §6.2~6.5/§7.2 |
| SYSTEM_RESERVE 延迟聚合 | 03 §7.5 | 01 §2.2, 04 §6.3 |
| OrderBook 内存结构 | 03 §3.1 | 04 §2.4/§3.2 |
| 事务回滚 evict + lazy rebuild | 04 §3.2 | 03 §2.1 (submit_order) |
| WAL 审计事件 | 04 §4 | 01 §2.8 (DDL) |
| 熔断触发条件 | 04 §5.2 | 01 §2.8 (circuit_breaker_events) |
| 市场状态机 | 01 §2.3 | 02 §8.3, 04 §2.4/§5.3 |
| 游标分页规范 | 02 §1.5 | — |
| 市场裁决与结算 | 02 §8.3 | 01 §2.3 (status/resolution_result) |

---

## 数据库表清单 (9 张)

| # | 表名 | 模块 | 定义 | 说明 |
|---|------|------|------|------|
| 1 | `users` | pm_gateway | 01 §2.1 | 用户注册/登录 |
| 2 | `accounts` | pm_account | 01 §2.2 | 资金账户 (含 SYSTEM_RESERVE, PLATFORM_FEE) |
| 3 | `markets` | pm_market | 01 §2.3 | 预测话题定义 + 单账本托管状态 |
| 4 | `orders` | pm_order | 01 §2.4 | 订单 (原始意图 + 订单簿视角 + 冻结) |
| 5 | `trades` | pm_clearing | 01 §2.5 | 成交记录 (含场景 + 已实现盈亏) |
| 6 | `positions` | pm_account | 01 §2.6 | 持仓 (YES/NO 合并行) |
| 7 | `ledger_entries` | pm_account | 01 §2.7 | 资金流水 (Append-Only) |
| 8 | `wal_events` | pm_matching | 01 §2.8 | 订单簿审计日志 (不参与恢复) |
| 9 | `circuit_breaker_events` | pm_matching | 01 §2.8 | 熔断事件记录 |

---

## 版本演进记录

| 文档 | 当前版本 | 版本历程 |
|------|---------|---------|
| 01 DB | v2.3 | v1.1 → v2.0(单账本重构) → v2.1(复式记账) → v2.2(realized_pnl) → v2.3(移除tick_size+审计表) |
| 02 API | v1.2 | v1.0 → v1.1(NO视角修正+幂等分流+游标分页+realized_pnl) → v1.2(tick_size+分页规范+冻结提示+裁决API) |
| 03 撮合 | v1.2 | v1.0 → v1.1(RESERVE延迟+排序注释) → v1.2(双侧退款+sync覆盖赋值+移除冗余DB写入) |
| 04 恢复 | v1.1 | v1.0(双路径恢复) → v1.1(砍掉快照+WAL恢复, 纯DB重建, 事务回滚保护) |
