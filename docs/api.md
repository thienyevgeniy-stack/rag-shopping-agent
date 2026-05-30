# API 说明

## `GET /health`

返回服务状态。

```json
{
  "status": "ok",
  "env": "development"
}
```

## `POST /chat`

请求：

```json
{
  "session_id": "demo",
  "message": "推荐一款适合油皮的洗面奶，预算100以内"
}
```

响应为 SSE：

```text
event: token
data: {"text":"根"}

event: product_card
data: {"id":"p001","name":"清爽控油氨基酸洗面奶","price":79}

event: done
data: {"session_id":"demo","filters":[],"exclusions":[]}
```

## 事件类型

| 事件 | 用途 |
|---|---|
| `token` | 文本增量渲染 |
| `product_card` | 商品卡片 |
| `done` | 本轮结束 |
| `cart_update` | 预留：购物车状态变化 |
| `comparison_card` | 预留：多商品对比 |
