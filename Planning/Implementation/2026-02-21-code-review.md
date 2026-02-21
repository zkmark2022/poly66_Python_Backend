# Module 5 全链路代码审查

> **目的**：验证 pm_risk / pm_matching / pm_clearing / pm_order 四个模块的代码逻辑正确性，并与设计文档保持一致。
>
> **断点续传**：每章完成后在对应状态栏打 ✅/❌，重启后从第一个未完成章节继续。
>
> **设计文档**：
> - `Planning/Detail_Design/01_全局约定与数据库设计.md` — DB schema, enum 定义
> - `Planning/Detail_Design/02_API接口契约.md` — REST API 契约
> - `Planning/Detail_Design/03_撮合引擎与清算流程设计.md` — 撮合/清算核心逻辑
> - `Planning/Detail_Design/04_WAL预写日志与故障恢复设计.md` — WAL 结构

---

## 审查章节总览

| 章节 | 模块 | 状态 | 主要问题数 |
|------|------|------|-----------|
| A | pm_risk (5个规则) | PENDING | — |
| B | pm_matching (OrderBook + Algo + Scenario) | PENDING | — |
| C | pm_clearing Part 1 (fee + ledger + WAL + MINT + TRANSFER) | PENDING | — |
| D | pm_clearing Part 2 (BURN + netting + invariants + settlement) | PENDING | — |
| E | pm_order (domain + transformer + repo + service + API) | PENDING | — |
| F | 跨模块一致性 (错误码 + 事务边界 + enum 对齐) | PENDING | — |

**说明**：章节 A、B、C/D、E 相互独立，可并行。章节 F 依赖 A-E 完成。

---

## 已知问题（审查前预修复）

这两个 Bug 已在审查前修复（commit `903c658`）：

| Bug | 文件 | 描述 |
|-----|------|------|
| `_INSERT_ORDER_SQL` 缺少 `price_type` 列名 | `src/pm_order/infrastructure/persistence.py` | VALUES 有 'LIMIT' 但列名没有 price_type |
| 事务从不提交 | `src/pm_order/application/service.py` | `async with db.begin()` 创建 SAVEPOINT 而非真实事务，缺少显式 commit |

---

## Chapter A：pm_risk 审查

**文件范围**：
- `src/pm_risk/rules/price_range.py`
- `src/pm_risk/rules/order_limit.py`
- `src/pm_risk/rules/self_trade.py`
- `src/pm_risk/rules/market_status.py`
- `src/pm_risk/rules/balance_check.py`

**设计参考**：
- `03_撮合引擎与清算流程设计.md` §1（风控规则）
- `02_API接口契约.md` §5（下单入参验证）
- `src/pm_common/errors.py`（错误码对照）

**检查项**：
- [ ] 价格范围：1-99 是否正确
- [ ] 数量限制：MAX_ORDER_QUANTITY 是否与设计一致
- [ ] 市场状态：错误码 3001/3002 是否正确
- [ ] 余额冻结：BUY 冻结公式 `original_price * qty + ceil_fee` 是否正确
- [ ] 仓位冻结：卖单 YES/NO shares 冻结逻辑是否正确
- [ ] TAKER_FEE_BPS=20：天花板除法 `(value * 20 + 9999) // 10000`

**状态**：PENDING

**审查结果**：

（待填写）

---

## Chapter B：pm_matching 审查

**文件范围**：
- `src/pm_matching/domain/models.py` (BookOrder, TradeResult)
- `src/pm_matching/engine/order_book.py` (OrderBook)
- `src/pm_matching/engine/scenario.py` (determine_scenario)
- `src/pm_matching/engine/matching_algo.py` (match_order)

**设计参考**：
- `03_撮合引擎与清算流程设计.md` §2（单边订单簿设计）、§3（撮合算法）

**检查项**：
- [ ] OrderBook：100 个价格槽，bids/asks 的 add/cancel 逻辑
- [ ] 最优价刷新：best_bid/best_ask 更新逻辑
- [ ] 4 种 scenario 判断矩阵是否与设计一致
- [ ] 撮合算法：BUY 匹配 asks（最低 ask ≤ book_price），SELL 匹配 bids（最高 bid ≥ book_price）
- [ ] 自我交易跳过：`deque.rotate(-1)` + `checked < total` 计数器
- [ ] TradeResult 字段完整性（buy_order_id, sell_order_id, price, qty, buy_user_id, sell_user_id, buy_book_type, sell_book_type, buy_original_price）

**状态**：PENDING

**审查结果**：

（待填写）

---

## Chapter C：pm_clearing Part 1 审查

**文件范围**：
- `src/pm_clearing/domain/fee.py`
- `src/pm_clearing/infrastructure/ledger.py`
- `src/pm_clearing/domain/scenarios/mint.py`
- `src/pm_clearing/domain/scenarios/transfer_yes.py`

**设计参考**：
- `03_撮合引擎与清算流程设计.md` §4（清算流程）、§5（费用计算）
- `04_WAL预写日志与故障恢复设计.md`（WAL 结构）

**检查项**：
- [ ] fee.py：get_fee_trade_value 各 book_type 分支逻辑
- [ ] fee.py：calc_fee 天花板除法
- [ ] fee.py：calc_released_cost 比例释放公式
- [ ] ledger.py：write_ledger SQL 参数名是否与 ledger_entries 表列名一致
- [ ] ledger.py：write_wal_event SQL 参数名是否与 wal_events 表列名一致
- [ ] MINT：reserve += qty*100, yes_shares += qty, no_shares += qty
- [ ] MINT：buyer 得 YES（credit yes_volume += qty），seller 得 NO（credit no_volume += qty）
- [ ] TRANSFER_YES：reserve 不变，卖方 yes_volume 减少，买方 yes_volume 增加

**状态**：PENDING

**审查结果**：

（待填写）

---

## Chapter D：pm_clearing Part 2 审查

**文件范围**：
- `src/pm_clearing/domain/scenarios/transfer_no.py`
- `src/pm_clearing/domain/scenarios/burn.py`
- `src/pm_clearing/domain/service.py`
- `src/pm_clearing/domain/netting.py`
- `src/pm_clearing/domain/invariants.py`
- `src/pm_clearing/domain/settlement.py`

**设计参考**：
- `03_撮合引擎与清算流程设计.md` §4、§6（净额结算）、§7（不变量）、§9（市场结算）

**检查项**：
- [ ] TRANSFER_NO：mirror of TRANSFER_YES，操作 NO 仓位
- [ ] BURN：reserve -= qty*100，yes/no shares 各减少
- [ ] service.py：scenario dispatch 是否与 determine_scenario 一致
- [ ] netting.py：`min(available_yes, available_no) * 100` 退款公式
- [ ] netting.py：position FOR UPDATE 是否防并发
- [ ] invariants.py：INV-1/2/3 三个断言 SQL 是否正确
- [ ] settlement.py：settle_market 各阶段逻辑

**状态**：PENDING

**审查结果**：

（待填写）

---

## Chapter E：pm_order 审查

**文件范围**：
- `src/pm_order/domain/models.py`
- `src/pm_order/domain/transformer.py`
- `src/pm_order/domain/repository.py`
- `src/pm_order/infrastructure/persistence.py`
- `src/pm_order/application/schemas.py`
- `src/pm_order/application/service.py`
- `src/pm_order/api/router.py`

**设计参考**：
- `02_API接口契约.md` §5（POST /orders）、§6（GET /orders）
- `03_撮合引擎与清算流程设计.md` §1（下单入口流程）

**检查项**：
- [ ] transformer.py：4 种转换矩阵（YES BUY→NATIVE_BUY, YES SELL→NATIVE_SELL, NO BUY→SYNTHETIC_SELL, NO SELL→SYNTHETIC_BUY）
- [ ] persistence.py：INSERT/UPDATE/SELECT SQL 列名与 orders 表 schema 一致
- [ ] schemas.py：PlaceOrderRequest 字段与 API 契约一致
- [ ] service.py：幂等性检查逻辑（4005 错误码）
- [ ] service.py：Order 对象构造是否完整
- [ ] router.py：HTTP method、status code、路由路径与设计文档一致

**状态**：PENDING

**审查结果**：

（待填写）

---

## Chapter F：跨模块一致性

**检查项**：
- [ ] 所有错误码与 `src/pm_common/errors.py` 中的定义一致
- [ ] 所有 enum 值与 `src/pm_common/enums.py` 中的定义一致
- [ ] MatchingEngine 链路中的函数签名调用顺序
- [ ] WAL event_type 字符串与设计文档约定一致

**状态**：PENDING

**审查结果**：

（待填写）

---

## 最终结论

（待填写）
