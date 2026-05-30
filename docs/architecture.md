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
  -> Doubao/Ark LLM 或模板 fallback
  -> SSE token/product_card/done
```

## 后端扩展点

- `VectorStore`：当前支持 `LocalJsonVectorStore` 和 `ChromaStore`。未安装 Chroma 或未启用时使用 JSON fallback；设置 `USE_CHROMA=true` 后走 Chroma。
- `ToolRegistry`：当前注册 `search_products`，后续增加 `add_to_cart`、`checkout`
- `InputProcessor`：当前是 `TextProcessor`，后续增加 `ASRProcessor`、`VLMProcessor`
- `PostProcessor`：当前有 `RangeFilter`、`ExclusionFilter`，后续增加 `ComparisonAggregator`
- `LLMClient`：当前支持 Ark OpenAI-compatible `/chat/completions` 流式接口；`USE_LLM=true` 且 `ARK_API_KEY` 存在时启用。
- SSE 事件：当前支持 `token`、`product_card`、`done`，后续增加 `cart_update`、`comparison_card`

## Chroma 接入

`server.rag.ingest` 会读取 `data/products_ref.json`，把统一商品文档写入 `server/chroma_db`。当前 embedding 使用本地 hashing embedding，用来先跑通向量库持久化链路；后续接 Doubao embedding 时只需要替换 `HashingEmbeddingFunction`。

## 防幻觉策略

最小闭环阶段先采用程序化约束：

- 回答只引用检索返回的商品卡片
- 检索为空时返回降级话术
- 价格、品牌、落地页来自 metadata，不由模型自由生成

接入大模型后，系统提示词仍要求只能依据检索上下文回答。

## Doubao/Ark 生成接入

`server.llm.ark_client.ArkChatClient` 负责调用 Ark OpenAI-compatible chat completions 接口。`server.llm.prompt` 会把检索得到的商品卡片整理为上下文，并在系统提示词中约束：

- 只能推荐候选商品中的商品
- 不编造优惠、库存、销量、功效或外部评价
- 价格、品牌、类目必须来自商品 metadata
- 候选商品不完全匹配时要如实说明

Orchestrator 会先完成 RAG 检索和后处理，再调用 LLM 生成自然语言回答。如果 LLM 未配置或调用失败，则回退到本地模板回答，保证 Demo 可用性。
