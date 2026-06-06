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
data: {"id":"p001","name":"清爽控油氨基酸洗面奶","price":79,"image_url":"http://127.0.0.1:8000/assets/products/p001_live.jpg","detail_url":"http://127.0.0.1:8000/products/p001"}

event: done
data: {"session_id":"demo","filters":[],"exclusions":[],"needs_clarification":false,"pending_subject":""}
```

## 事件类型

| 事件 | 用途 |
|---|---|
| `token` | 文本增量渲染 |
| `product_card` | 商品卡片 |
| `done` | 本轮结束 |
| `cart_update` | 购物车状态变化 |
| `comparison_card` | 多商品对比结构化结果 |

`done` 事件中的 `needs_clarification=true` 表示本轮是主动澄清，不会返回商品卡片；`pending_subject` 会保留待补全的商品主题，例如“手机”。

购物车请求会额外返回 `cart_update`，例如：

```text
event: cart_update
data: {
  "items": [
    {"product_id":"p_beauty_021","name":"科颜氏牛油果保湿眼霜","price":210,"quantity":1}
  ],
  "total_quantity": 1,
  "total_price": 210,
  "is_empty": false
}
```

对比请求会额外返回 `comparison_card`，例如：

```text
event: comparison_card
data: {
  "title": "商品对比",
  "query": "科颜氏和AHC哪个眼霜更适合干皮",
  "products": [
    {"id":"p_beauty_021","brand":"科颜氏","price":210,"strengths":["保湿"]},
    {"id":"p_beauty_016","brand":"AHC","price":139,"strengths":["保湿","修护"]}
  ],
  "recommendation": {"product_id":"p_beauty_021","focus":"保湿/干皮"}
}
```

## 静态资源

### `GET /assets/products/{filename}`

返回参考集商品主图，例如：

```text
GET /assets/products/p_beauty_021_live.jpg
```

商品卡片中的 `image_url` 会直接指向该路径。真机调试时需要先执行：

```powershell
D:\Android\Sdk\platform-tools\adb.exe reverse tcp:8000 tcp:8000
```

## 商品详情页

### `GET /products/{product_id}`

返回本地商品详情 HTML 页面，例如：

```text
GET /products/p_beauty_021
```

商品卡片中的 `detail_url` 会指向该页面。当前页面展示商品主图、名称、品牌、类目、价格、库存、标签、规格和商品说明。
