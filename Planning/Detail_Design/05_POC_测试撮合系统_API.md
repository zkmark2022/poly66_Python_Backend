# PM-JC-WS 接口文档

> 本文档基于 bot 文件夹下的 Python 代码自动解析生成

---

## 目录

1. [概述](#概述)
2. [认证机制](#认证机制)
3. [REST API 接口](#rest-api-接口)
   - [认证接口](#1-认证接口)
   - [市场接口](#2-市场接口)
   - [订单簿接口](#3-订单簿接口)
   - [订单接口](#4-订单接口)
   - [做市商接口](#5-做市商接口)
4. [WebSocket 接口](#websocket-接口)
5. [Kafka 命令接口](#kafka-命令接口)
6. [配置参数](#配置参数)
7. [错误处理](#错误处理)

---

## 概述

PM-JC-WS 系统采用**混合接口架构**：

| 接口类型 | 用途 | 协议 |
|----------|------|------|
| REST API | 用户交互、配置管理 | HTTP/HTTPS |
| WebSocket | 实时数据推送 | STOMP over WebSocket |
| Kafka | 异步事件处理 | Kafka Producer/Consumer |

---

## 认证机制

- **方式**: Bearer Token (JWT)
- **获取**: 通过 `POST /api/auth/login` 登录获取
- **使用**: 在请求头中添加 `Authorization: Bearer {token}`

### 需要认证的端点

- `GET /api/orderbook/{id}`
- `POST /api/orders`
- `GET /api/orders/active`
- `DELETE /api/orders/{id}`
- `POST /api/market-maker`
- `POST /api/market-maker/run`

---

## REST API 接口

### 1. 认证接口

#### POST /api/auth/register

用户注册

**请求参数**:
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

**响应**: 用户对象或错误信息

---

#### POST /api/auth/login

用户登录

**请求参数**:
```json
{
  "username": "string",
  "password": "string"
}
```

**响应**:
```json
{
  "token": "Bearer token string"
}
```

---

### 2. 市场接口

#### GET /api/markets

获取市场列表（支持分页）

**查询参数**:

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| status | string | 市场状态过滤 | `OPEN` |
| page | int | 页码（从0开始）| `0` |
| size | int | 每页数量 | `200` |

**响应**:
```json
{
  "content": [
    {
      "id": "market_id",
      "title": "市场标题",
      "description": "市场描述",
      "yesPrice": 50.0,
      "yesSymbolId": "yes_symbol_id",
      "noSymbolId": "no_symbol_id"
    }
  ],
  "last": true,
  "totalPages": 1
}
```

---

#### GET /api/markets/{marketId}

获取单个市场详情

**路径参数**:
- `marketId`: 市场ID

**响应**: 市场对象

---

#### POST /api/markets

创建新市场

**请求参数**:
```json
{
  "title": "市场标题",
  "description": "市场描述",
  "category": "分类",
  "resolutionDate": "2030-01-01T00:00:00"
}
```

**响应**: 创建的市场对象（包含 id）

---

#### GET /api/markets/{marketId}/trades

获取市场最近交易历史

**路径参数**:
- `marketId`: 市场ID

**查询参数**:

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| limit | int | 返回最近N条交易 | `30` |

**响应**:
```json
[
  {
    "price": 50.0,
    "quantity": 10
  }
]
```

---

### 3. 订单簿接口

#### GET /api/orderbook/{marketId}

获取市场订单簿

**需要认证**: 是

**路径参数**:
- `marketId`: 市场ID

**查询参数**:

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| depth | int | 订单簿深度 | `20` |
| excludeMarketMaker | bool | 排除做市商单 | `false` |

**响应**:
```json
{
  "yesBids": [
    {
      "quantity": 10,
      "price": 50.0
    }
  ],
  "yesAsks": [
    {
      "quantity": 10,
      "price": 51.0
    }
  ]
}
```

---

### 4. 订单接口

#### POST /api/orders

下单

**需要认证**: 是

**请求参数**:
```json
{
  "marketId": 1,
  "side": "YES",
  "action": "BUY",
  "orderType": "LIMIT",
  "price": 50.0,
  "quantity": 10
}
```

**参数说明**:

| 字段 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| marketId | int | - | 市场ID |
| side | string | `YES`, `NO` | 合约方向 |
| action | string | `BUY`, `SELL` | 买卖方向 |
| orderType | string | `LIMIT`, `MARKET`, `IOC`, `FOK` | 订单类型 |
| price | float | 0-100 | 价格（限价单必填）|
| quantity | int | >0 | 数量 |

**响应**:
```json
{
  "id": "order_id",
  "status": "OPEN"
}
```

**订单状态说明**:
- `OPEN`: 未成交
- `PARTIALLY_FILLED`: 部分成交
- `FILLED`: 完全成交
- `CANCELLED`: 已取消

---

#### GET /api/orders/active

获取用户所有活跃订单

**需要认证**: 是

**响应**:
```json
[
  {
    "id": "order_id",
    "status": "OPEN"
  }
]
```

---

#### DELETE /api/orders/{orderId}

取消订单

**需要认证**: 是

**路径参数**:
- `orderId`: 订单ID

**响应**:
```json
{
  "status": "CANCELLED"
}
```

---

### 5. 做市商接口

#### POST /api/market-maker

配置做市商参数

**需要认证**: 是（需要 `ADMIN` 或 `MARKET_MAKER` 角色）

**请求参数**（全部可选，支持部分更新）:
```json
{
  "enabled": true,
  "marketId": 5,
  "orderSize": 10,
  "spread": 2.0,
  "refreshMs": 3000,
  "enforceInventory": true,
  "maxYesPosition": 100000,
  "maxNoPosition": 100000,
  "minBalanceCents": 0,
  "autoTopUp": true,
  "priceShift": 0.0
}
```

**参数说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| enabled | bool | 是否启用做市 |
| marketId | int | 目标市场ID |
| orderSize | int | 每单数量 |
| spread | float | 买卖价差 |
| refreshMs | int | 刷新间隔（毫秒）|
| enforceInventory | bool | 是否限制库存 |
| maxYesPosition | int | 最大YES持仓 |
| maxNoPosition | int | 最大NO持仓 |
| minBalanceCents | int | 最小账户余额（分）|
| autoTopUp | bool | 自动充值 |
| priceShift | float | 价格偏移 |

**响应**: 配置确认

---

#### POST /api/market-maker/run

执行做市操作

**需要认证**: 是（需要 `ADMIN` 或 `MARKET_MAKER` 角色）

**查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| marketId | int | 目标市场ID |
| minBalanceCents | int | 最小账户余额（可选）|

**响应**:
```json
{
  "summary": {
    "yesBuyPrices": [45.0, 46.0],
    "yesSellPrices": [51.0, 52.0],
    "noBuyPrices": [30.0, 31.0],
    "noSellPrices": [55.0, 56.0]
  }
}
```

---

## WebSocket 接口

### 连接信息

| 属性 | 值 |
|------|-----|
| URL | `ws://host:port/ws/websocket` |
| HTTPS | `wss://host:port/ws/websocket` |
| 协议 | STOMP 1.1/1.2 |

### 连接流程

**1. CONNECT**
```
CONNECT
accept-version:1.1,1.2
heart-beat:10000,10000

\x00
```

**2. SUBSCRIBE**
```
SUBSCRIBE
id:sub-0
destination:{destination}
ack:auto

\x00
```

### 可订阅主题

| 主题 | 用途 | 数据格式 |
|------|------|----------|
| `/topic/prices/all` | 所有市场价格更新 | 价格数据 |
| `/topic/market/{marketId}/price` | 特定市场价格更新 | 市场价格 |
| `/topic/market/{marketId}/orderbook` | 特定市场订单簿 | 订单簿快照 |

### 消息格式示例

```
MESSAGE
message-id:...
destination:/topic/market/1/price
content-type:application/json

{
  "marketId": 1,
  "yesPrice": 50.0,
  "noPrice": 50.0,
  "timestamp": 1234567890
}
\x00
```

---

## Kafka 命令接口

### Kafka 配置

| 配置项 | 默认值 |
|--------|--------|
| KAFKA_BOOTSTRAP | `localhost:9092` |
| KAFKA_TOPIC_COMMANDS | `pm.commands` |
| KAFKA_TOPIC_COMMAND_RESULTS | `pm.results` |
| KAFKA_TOPIC_TRADES | `pm.events.trade` |
| KAFKA_TOPIC_ORDERBOOK | `pm.events.orderbook` |
| KAFKA_TOPIC_PRICES | `pm.events.price` |
| KAFKA_TOPIC_MARKET_MAKER_AUDIT | `pm.audit.market_maker` |

### 命令格式

所有命令发送到 `pm.commands` 主题，结果从 `pm.results` 主题读取。

**通用命令结构**:
```json
{
  "commandId": "uuid",
  "type": "COMMAND_TYPE",
  "payload": { ... },
  "timestamp": 1234567890
}
```

---

### CREATE_USER

创建用户

**Payload**:
```json
{
  "guuid": "username",
  "email": "user@example.com",
  "password": "password123"
}
```

---

### CREATE_MARKET

创建市场

**Payload**:
```json
{
  "title": "Market Title",
  "description": "Description",
  "category": "general",
  "resolutionDate": "2030-01-01T00:00:00"
}
```

**返回**:
```json
{
  "id": 1,
  "yesSymbolId": "yes_symbol_123",
  "noSymbolId": "no_symbol_456",
  "market": { }
}
```

---

### PLACE_ORDER

下单

**Payload**:
```json
{
  "username": "trader1",
  "marketId": 1,
  "side": "YES",
  "action": "BUY",
  "orderType": "LIMIT",
  "price": 50.0,
  "quantity": 10
}
```

**返回**:
```json
{
  "id": "order_id"
}
```

---

### CANCEL_ORDER

取消订单

**Payload**:
```json
{
  "username": "trader1",
  "orderId": 123
}
```

**返回**:
```json
{
  "status": "SUCCESS",
  "message": "Order cancelled"
}
```

---

### SET_MARKET_MAKER

配置做市商

**Payload**:
```json
{
  "enabled": true,
  "marketId": 1,
  "orderSize": 5,
  "spread": 2.0,
  "minBalanceCents": 0,
  "autoTopUp": true
}
```

---

### RUN_MARKET_MAKER

执行做市

**Payload**:
```json
{
  "marketId": 1,
  "minBalanceCents": 0
}
```

**返回**:
```json
{
  "data": {
    "summary": {
      "yesBuyPrices": [45.0, 46.0],
      "yesSellPrices": [51.0, 52.0],
      "noBuyPrices": [30.0, 31.0],
      "noSellPrices": [55.0, 56.0]
    }
  }
}
```

---

### ADJUST_BALANCE

调整用户余额

**Payload（二选一）**:
```json
{
  "amountInCents": 1000000,
  "userId": 123
}
```
或
```json
{
  "amountInCents": 1000000,
  "exchangeUid": "string"
}
```

---

### Kafka 事件流

| 主题 | 事件类型 | 用途 |
|------|----------|------|
| `pm.events.trade` | TRADE | 订单成交通知 |
| `pm.audit.market_maker` | PLACE/FILL/CANCEL | 做市商审计日志 |

**审计日志结构**:
```json
{
  "marketId": 1,
  "eventType": "PLACE",
  "status": "OPEN",
  "side": "YES",
  "action": "BUY",
  "price": 50.0,
  "quantity": 10
}
```

---

## 配置参数

### mm_bot.py 配置文件 (config.json)

```json
{
  "base_url": "http://localhost:8080",
  "admin_username": "admin",
  "admin_password": "admin123",
  "poll_interval_sec": 5,
  "market_ids": [],
  "orderbook_depth": 20,
  "trade_lookback": 30,
  "spread_base": 2.0,
  "spread_min": 1.0,
  "spread_max": 8.0,
  "vol_weight": 1.5,
  "order_size_base": 10,
  "order_size_min": 2,
  "order_size_max": 50,
  "enforce_inventory": true,
  "max_yes_position": 100000,
  "max_no_position": 100000,
  "min_balance_cents": 0
}
```

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| base_url | string | API 基础地址 |
| admin_username | string | 管理员用户名 |
| admin_password | string | 管理员密码 |
| poll_interval_sec | int | 轮询间隔（秒）|
| market_ids | array | 指定市场ID列表（空则全部）|
| orderbook_depth | int | 订单簿查询深度 |
| trade_lookback | int | 交易历史查询数量 |
| spread_base | float | 基础价差 |
| spread_min | float | 最小价差 |
| spread_max | float | 最大价差 |
| vol_weight | float | 波动率权重 |
| order_size_base | int | 基础订单大小 |
| order_size_min | int | 最小订单大小 |
| order_size_max | int | 最大订单大小 |
| enforce_inventory | bool | 是否限制库存 |
| max_yes_position | int | 最大YES持仓 |
| max_no_position | int | 最大NO持仓 |
| min_balance_cents | int | 最小账户余额（分）|

---

## 错误处理

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证（token过期或无效）|
| 403 | 权限不足（需要特定角色）|
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 重试策略

- Kafka 命令默认超时: 20秒
- HTTP 请求默认超时: 30秒
- 网络错误最多重试5次后退避

---

## 调用流程示例

### 完整用户交易流程

```python
# 1. 注册/登录
POST /api/auth/register  # 创建用户
POST /api/auth/login     # 获取 token

# 2. 获取市场信息
GET /api/markets?status=OPEN       # 获取开放市场列表
GET /api/markets/{id}/trades       # 获取交易历史
GET /api/orderbook/{id}            # 获取订单簿

# 3. 交易操作
POST /api/orders                   # 下单
GET /api/orders/active             # 查看活跃订单
DELETE /api/orders/{id}            # 取消订单

# 4. 做市操作（需要 MARKET_MAKER 角色）
POST /api/market-maker             # 配置做市参数
POST /api/market-maker/run         # 执行做市

# 5. 实时数据订阅
WebSocket /ws/websocket            # 订阅价格/订单簿更新
```

---

## 文件位置参考

| 文件 | 路径 | 用途 |
|------|------|------|
| mm_bot.py | `bot/` | 市场做市机器人 |
| config.json | `bot/` | 做市机器人配置 |
| batch_orders.py | `pm-jc-ws/.../scripts/batch_tools/` | 批量订单工具 |
| common.py | `pm-jc-ws/.../scripts/kafka/` | Kafka 通用工具 |
| send_*.py | `pm-jc-ws/.../scripts/kafka/` | Kafka 命令发送脚本 |

---

*文档生成时间: 2026-02-26*
