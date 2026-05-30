# 架构设计

## 目标

先完成可演示的最小闭环，再逐步增强多轮对话、反选、多模态和购物车能力。

## 主链路

```text
Android Compose
  -> OkHttp SSE
  -> FastAPI /chat
  -> Orchestrator
  -> ToolRegistry.search_products
  -> VectorStore
  -> PostProcessor
  -> SSE token/product_card/done
```

## 后端扩展点

- `VectorStore`：当前支持 `LocalJsonVectorStore` 和 `ChromaStore`。未安装 Chroma 或未启用时使用 JSON fallback；设置 `USE_CHROMA=true` 后走 Chroma。
- `ToolRegistry`：当前注册 `search_products`，后续增加 `add_to_cart`、`checkout`
- `InputProcessor`：当前是 `TextProcessor`，后续增加 `ASRProcessor`、`VLMProcessor`
- `PostProcessor`：当前有 `RangeFilter`、`ExclusionFilter`，后续增加 `ComparisonAggregator`
- SSE 事件：当前支持 `token`、`product_card`、`done`，后续增加 `cart_update`、`comparison_card`

## Chroma 接入

`server.rag.ingest` 会读取 `data/products_ref.json`，把统一商品文档写入 `server/chroma_db`。当前 embedding 使用本地 hashing embedding，用来先跑通向量库持久化链路；后续接 Doubao embedding 时只需要替换 `HashingEmbeddingFunction`。

## 防幻觉策略

最小闭环阶段先采用程序化约束：

- 回答只引用检索返回的商品卡片
- 检索为空时返回降级话术
- 价格、品牌、落地页来自 metadata，不由模型自由生成

接入大模型后，系统提示词仍要求只能依据检索上下文回答。
