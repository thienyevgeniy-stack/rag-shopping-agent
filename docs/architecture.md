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
  -> /assets/products 商品主图
  -> /products/{id} 商品详情页
```

## 后端扩展点

- `VectorStore`：当前支持 `LocalJsonVectorStore` 和 `ChromaStore`。未安装 Chroma 或未启用时使用 JSON fallback；设置 `USE_CHROMA=true` 后走 Chroma。
- `ToolRegistry`：当前注册 `search_products` 和 `compare_products`，后续增加 `add_to_cart`、`checkout`
- `InputProcessor`：当前是 `TextProcessor`，后续增加 `ASRProcessor`、`VLMProcessor`
- `PostProcessor`：当前有 `RangeFilter`、`KeywordFilter`、`ExclusionFilter`
- `LLMClient`：当前支持 Ark OpenAI-compatible `/chat/completions` 流式接口；`USE_LLM=true` 且 `ARK_API_KEY` 存在时启用。
- `StaticFiles`：当前通过 `/assets/products/{filename}` 服务参考集商品主图。
- `Products API`：当前通过 `/products/{product_id}` 提供本地商品详情 HTML 页。
- SSE 事件：当前支持 `token`、`product_card`、`comparison_card`、`done`，后续增加 `cart_update`

## Chroma 接入

`server.rag.ingest` 会读取 `data/products_ref.json`，把统一商品文档写入 `server/chroma_db`。默认 embedding 使用本地 hashing embedding，便于离线测试和无 API Key 启动。

如果 `.env` 或环境变量设置 `USE_ARK_EMBEDDING=true` 且存在 `ARK_API_KEY`，Chroma 会使用 `ArkEmbeddingFunction` 调用 Ark OpenAI-compatible `/embeddings` 接口。默认 `EMBEDDING_BATCH_SIZE=4`，贴近方舟文本向量化文档的性能建议。为避免旧 hashing 向量和真实 embedding 维度冲突，真实 embedding 会写入带模型名后缀的独立 collection，例如：

```text
products_ark_embedding_doubao_embedding_text_240515
```

切换 embedding 后需要重新执行：

```powershell
python -m server.rag.ingest
```

## 防幻觉策略

最小闭环阶段先采用程序化约束：

- 回答只引用检索返回的商品卡片
- 检索为空时返回降级话术
- 价格、品牌、落地页来自 metadata，不由模型自由生成

接入大模型后，系统提示词仍要求只能依据检索上下文回答。

## 主动澄清与多轮改写

对于过宽泛且缺少预算/偏好的请求，Orchestrator 会先返回澄清问题，而不是直接检索并硬推商品。例如：

```text
用户：推荐一款手机
助手：你更看重拍照、续航、性能还是性价比？预算大概是多少？
```

澄清时 `done` 事件会带上 `needs_clarification=true` 和 `pending_subject`。用户下一轮回答“拍照优先，预算4000”时，`rewrite_query` 会把上一轮的“手机”补回查询，形成更完整的检索表达。

## 商品对比

`compare_products` 复用 `ProductSearchTool`，但会先解析“X 和 Y / X vs Y / X 与 Y”这类品牌或商品对，再分别检索两侧候选，避免普通 Top-K 只召回一侧品牌。对比场景会保留双方候选用于解释差异；如果用户给出预算，结论会优先推荐预算内商品，同时在 tradeoffs 中标记超预算候选。

对比链路返回三类 SSE：

- `token`：确定性对比回答，关闭 LLM 时也可稳定演示。
- `product_card`：两侧候选商品卡片。
- `comparison_card`：结构化对比数据，Android 端会渲染为对比面板。

## Doubao/Ark 生成接入

`server.llm.ark_client.ArkChatClient` 负责调用 Ark OpenAI-compatible chat completions 接口。`server.llm.prompt` 会把检索得到的商品卡片整理为上下文，并在系统提示词中约束：

- 只能推荐候选商品中的商品
- 不编造优惠、库存、销量、功效或外部评价
- 价格、品牌、类目必须来自商品 metadata
- 候选商品不完全匹配时要如实说明

Orchestrator 会先完成 RAG 检索和后处理，再调用 LLM 生成自然语言回答。如果 LLM 未配置或调用失败，则回退到本地模板回答，保证 Demo 可用性。

## 商品主图链路

`scripts.extract_ref_images` 会从参考数据集 zip 中抽取商品图片到 `data/product_images`。FastAPI 将该目录挂载到 `/assets/products`，`ProductSearchTool` 会把商品 metadata 中的相对图片路径转换为完整 URL，例如：

```text
http://127.0.0.1:8000/assets/products/p_beauty_021_live.jpg
```

真机调试时该 URL 通过 `adb reverse tcp:8000 tcp:8000` 被手机访问。Android 端使用 Coil 加载商品图片，点击商品卡片时打开本地详情弹窗；收到 `comparison_card` 时会展示对比面板。

商品卡片中的 `detail_url` 指向本地商品详情页：

```text
http://127.0.0.1:8000/products/p_beauty_021
```

Android 详情弹窗中的“打开链接”会跳转到该页面，用于满足 Demo 中可点击商品落地页的基础要求。
