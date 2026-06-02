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
data: {"id":"p001","name":"清爽控油氨基酸洗面奶","price":79,"image_url":"http://127.0.0.1:8000/assets/products/p001_live.jpg"}

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
