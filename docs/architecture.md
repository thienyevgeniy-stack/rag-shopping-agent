# 架构设计

## 目标

先完成可演示的最小闭环，再逐步增强多轮对话、反选、商品对比、购物车和多模态能力。

## 主链路

```text
Android Compose
  -> OkHttp SSE
  -> FastAPI /chat
  -> Orchestrator
  -> SemanticPlanner
  -> AgentWorkflow
  -> Clarification/Cart/Compare/Context/Recommendation Handler
  -> ToolRegistry.search_products
  -> VectorStore
  -> PostProcessor
  -> Doubao/Ark LLM 或模板 fallback
  -> SSE token/product_card/comparison_card/cart_update/done
  -> /assets/products 商品主图
  -> /products/{id} 商品详情页
```

## 后端扩展点

- `VectorStore`：当前支持 `LocalJsonVectorStore` 和 `ChromaStore`。未安装 Chroma 或未启用时使用 JSON fallback；设置 `USE_CHROMA=true` 后走 Chroma。
- `SemanticPlanner`：先把用户自然语言解析为结构化 `SemanticPlan`。LLM 可用时尝试 JSON plan，失败或不可用时走规则 fallback；后端再用 Pydantic 校验和工具执行，避免模型直接改状态。
- `AgentWorkflow`：当前是轻量内部工作流，按澄清、购物车、对比、上下文追问、普通推荐的优先级分派；后续可替换为 LangChain/LangGraph 类 planner，而不影响 API 和 Android 端协议。
- `ToolRegistry`：当前注册 `search_products`、`compare_products` 和 `manage_cart`
- `InputProcessor`：当前是 `TextProcessor`，后续增加 `ASRProcessor`、`VLMProcessor`
- `PostProcessor`：当前有 `RangeFilter`、`KeywordFilter`、`ExclusionFilter`
- `LLMClient`：当前支持 Ark OpenAI-compatible `/chat/completions` 流式接口；`USE_LLM=true` 且 `ARK_API_KEY` 存在时启用。
- `StaticFiles`：当前通过 `/assets/products/{filename}` 服务参考集商品主图。
- `Products API`：当前通过 `/products/{product_id}` 提供本地商品详情 HTML 页。
- SSE 事件：当前支持 `token`、`product_card`、`comparison_card`、`cart_update`、`done`

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

对于过宽泛且缺少预算/偏好的请求，`ClarificationHandler` 会先返回澄清问题，而不是直接检索并硬推商品。例如：

```text
用户：推荐一款手机
助手：你更看重拍照、续航、性能还是性价比？预算大概是多少？
```

澄清时 `done` 事件会带上 `needs_clarification=true` 和 `pending_subject`。用户下一轮回答“拍照优先，预算4000”时，`rewrite_query` 会把上一轮的“手机”补回查询，形成更完整的检索表达。

会话状态会保留上一轮候选商品卡片，`ContextFollowUpHandler` 用它处理轻量上下文追问：

- `第二个怎么样`：直接围绕上一轮第二个候选商品回答，并重新返回该商品卡片。
- `这个适合干皮吗`：把“这个/它/那款”解析为上一轮首个候选商品，基于商品 metadata 给出回答。
- `再便宜点`：根据上一轮候选中的最低价自动追加更低的预算过滤条件，再进入检索。
- `AHC 那个熬夜党能用吗`：通过品牌/名称引用上一轮候选商品，不再只依赖“第二个”这类固定句式。
- `那支给我来两件`：通过结构化 plan 识别隐式加购和数量。
- `有没有比第二款更适合敏感肌但别太贵的`：把“第二款”解析为参考商品，并转换成敏感肌关键词和参考价格上限后重新检索。

## 语义规划层

`server.agent.semantic.SemanticPlanner` 是当前从 Demo 走向成熟 Agent 的关键层。默认使用快速规则 fallback；当 `.env` 或环境变量设置 `USE_SEMANTIC_LLM=true` 且 `USE_LLM=true` 时，会先尝试 LLM JSON plan，失败后仍回退规则解析。它输出的 `SemanticPlan` 包括：

- `intent`：recommend / compare / cart / ask_product_detail / clarify / browse
- `cart_action`：add / remove / update_quantity / view / checkout
- `reference_type`：last / ordinal / name / brand / cheapest
- `reference_text`、`reference_index`、`quantity`
- `filters`：keyword / max_price / exclude
- `query` 和 `needs_search`

LLM plan 只作为语义理解建议，所有字段都要经过 Pydantic 校验；业务动作仍由 handler 和 tool 执行。这样比单纯堆正则更有泛化能力，也比让 LLM 直接调用业务动作更安全。

## 商品对比

`compare_products` 复用 `ProductSearchTool`，但会先解析“X 和 Y / X vs Y / X 与 Y”这类品牌或商品对，再分别检索两侧候选，避免普通 Top-K 只召回一侧品牌。对比场景会保留双方候选用于解释差异；如果用户给出预算，结论会优先推荐预算内商品，同时在 tradeoffs 中标记超预算候选。

对比链路返回三类 SSE：

- `token`：确定性对比回答，关闭 LLM 时也可稳定演示。
- `product_card`：两侧候选商品卡片。
- `comparison_card`：结构化对比数据，Android 端会渲染为对比面板。

## 对话式购物车

`manage_cart` 直接操作 `SessionState.cart`，并复用上一轮 `candidate_product_cards`。用户可以说“把刚才那款加到购物车”“把第二个加到购物车”“删除第一个”“把数量改成 2”“查看购物车”等自然语言指令。每次购物车状态变化后，后端会返回：

- `token`：对购物车动作的自然语言确认。
- `cart_update`：结构化购物车状态，包括商品列表、总件数和总价。
- `done`：本轮结束。

Android 端收到 `cart_update` 后会展示购物车面板；面板中的商品行可点击打开详情弹窗，满足 PDF 中“结构化数据 CRUD 并在客户端实时反馈状态变化”的加分项方向。

## Doubao/Ark 生成接入

`server.llm.ark_client.ArkChatClient` 负责调用 Ark OpenAI-compatible chat completions 接口。`server.llm.prompt` 会把检索得到的商品卡片整理为上下文，并在系统提示词中约束：

- 只能推荐候选商品中的商品
- 不编造优惠、库存、销量、功效或外部评价
- 价格、品牌、类目必须来自商品 metadata
- 候选商品不完全匹配时要如实说明

`RecommendationHandler` 会先完成 RAG 检索和后处理，再调用 LLM 生成自然语言回答。如果 LLM 未配置或调用失败，则回退到本地模板回答，保证 Demo 可用性。

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
