# 项目进度

更新时间：2026-06-07

## 已完成

- [x] 建立 Git 仓库和 monorepo 目录结构
- [x] 配置 `.gitignore`，排除 `.env`、PDF、构建产物、日志和缓存
- [x] FastAPI 后端骨架
- [x] `/health` 健康检查
- [x] `/chat` SSE 流式接口
- [x] SSE 事件：`token` / `product_card` / `done`
- [x] 本地 JSON 商品检索 fallback
- [x] 商品预算过滤
- [x] 反选/排除过滤
- [x] SessionState 会话状态结构
- [x] ToolRegistry 工具注册结构
- [x] VectorStore / InputProcessor / PostProcessor 扩展接口
- [x] Android Kotlin + Compose 原生客户端骨架
- [x] Android SSE 网络客户端
- [x] Android 对话 UI、输入框、流式消息气泡
- [x] Android 商品卡片展示和点击跳转
- [x] Android 商品卡片主图展示
- [x] Android 商品详情弹窗
- [x] 本地商品详情页 `/products/{product_id}`
- [x] 后端 pytest 测试
- [x] 后端联调测试脚本
- [x] Android 环境检查脚本
- [x] README、架构文档、API 文档、Demo 脚本
- [x] Android Studio、Android SDK、Platform Tools、API 35 安装到 D 盘
- [x] 真机识别与 `adb reverse tcp:8000 tcp:8000`
- [x] 真机端到端 Demo 跑通：输入推荐需求后返回 PureLab 商品卡片
- [x] 接入参考数据集 zip，清洗生成 100 条正式商品数据
- [x] 后端默认数据源切换为 `data/products_ref.json`
- [x] 增加关键词后处理，减少跨类目误召回
- [x] ChromaStore 适配层
- [x] Chroma 灌库脚本 `python -m server.rag.ingest`
- [x] `USE_CHROMA=true` 可启用 Chroma，默认保留 JSON fallback
- [x] Ark/Doubao embedding 适配：`USE_ARK_EMBEDDING=true` 时 Chroma 使用 Ark `/embeddings`
- [x] embedding collection 隔离：真实 embedding 使用模型名后缀 collection，避免与本地 hashing 向量维度冲突
- [x] 已完成 Git 提交，当前最新提交覆盖：MVP、Chroma、反选约束、Doubao/Ark、商品主图、商品详情页
- [x] 严格关键词过滤：无严格匹配时降级说明，不返回无关商品
- [x] 一句话多重反选解析：如“不要含酒精的，也不要日系品牌”
- [x] Doubao/Ark LLM 客户端接入：`USE_LLM=true` 时基于 RAG 商品上下文生成回答
- [x] LLM 调用失败或未配置 API Key 时自动回退本地模板回答
- [x] 防幻觉 prompt：约束只基于候选商品回答，不编造价格、优惠、库存或功效
- [x] 从参考集 zip 抽取 100 张商品主图到 `data/product_images`
- [x] FastAPI 通过 `/assets/products/...` 提供商品主图静态资源
- [x] 商品卡片返回完整 `detail_url`，支持跳转本地商品详情页
- [x] 主动澄清：如“推荐一款手机”会先追问拍照/续航/性能/性价比和预算
- [x] 多轮改写补全：澄清后的下一轮会把 `pending_subject` 补回查询
- [x] 上下文追问增强：支持“第二个怎么样”“这个适合吗”“再便宜点”等轻量跟进
- [x] 预算解析增强：支持“预算4000”这类预算前置表达，并继续由程序化价格过滤执行
- [x] 商品对比：识别“X 和 Y / X vs Y / X 与 Y”，分别检索双方候选并返回 `comparison_card`
- [x] 对比预算处理：对比时保留双方候选解释差异，推荐结论优先选择预算内商品
- [x] Android 端渲染 `comparison_card`：展示推荐结论、关注点、双方优势和取舍
- [x] 对话式购物车：支持加购、查看、删除、修改数量和模拟下单确认
- [x] Android 端渲染 `cart_update`：展示购物车总件数、总价和最近商品，商品行可点击打开详情
- [x] 后端智能体工程化拆分：Orchestrator 收窄为预处理和调度层，具体任务由 `AgentWorkflow` 和 handlers 承接
- [x] 外部 RAG/Agent 成熟化参考梳理：新增 `docs/rag_product_maturity.md`
- [x] 新增 `SemanticPlanner`：规则 fallback 默认启用，`USE_SEMANTIC_LLM=true` 时支持 LLM JSON plan + Pydantic 校验
- [x] 上下文泛化增强：支持品牌/名称引用、隐式加购数量、候选商品排除、参考价格继续检索
- [x] Agent trace：每轮记录 plan、handler、query、filters、事件计数、商品 ID、购物车数量和耗时
- [x] 调试接口：`GET /debug/traces` 和 `GET /debug/traces/{trace_id}`
- [x] 离线评估集和脚本：`data/eval_queries.jsonl`、`python scripts/evaluate_agent.py`
- [x] 商品 taxonomy/facet 过滤：`data/product_taxonomy.json` 维护标准 `product_type`，支持别名和组合触发词，检索文档加载时写入类型元数据，`运动鞋/跑鞋/跑步鞋/跑步的鞋` 不再混入运动裤、短裤等同大类商品
- [x] 同 facet 多选 OR：`运动鞋或运动裤` 会返回鞋或裤，不要求一个商品同时满足两个类型

## 已验证

- [x] `python -m compileall server`
- [x] `python -m pytest server/tests -q`
- [x] `/chat` 能返回流式 token 和商品卡片
- [x] 空检索结果会降级说明，不返回虚假商品卡片
- [x] Android Studio Gradle Sync 成功
- [x] 小米真机安装成功
- [x] 手机 App 输入后能通过后端返回 PureLab 商品结果
- [x] 参考集查询验证：保湿眼霜可返回科颜氏/AHC 商品卡片
- [x] PDF 典型多轮场景回归：跑鞋 -> 轻量 -> 预算 500 以内，无严格匹配时不返回食品等无关商品
- [x] LLM mock 测试：正常流式生成、失败回退、无商品时跳过 LLM
- [x] Doubao-Seed 真实接口联调完成：`doubao-seed-2-0-lite-260215`
- [x] 静态图片接口验证：`/assets/products/p_beauty_021_live.jpg`
- [x] 商品详情页接口验证：`/products/p_beauty_021`
- [x] Android Debug 构建和真机安装成功
- [x] Ark embedding mock 测试：OpenAI-compatible `/embeddings` 请求、batching、index 顺序解析
- [x] 主动澄清回归：宽泛手机推荐不返回商品卡片，`done` 返回 `needs_clarification=true`
- [x] 多轮预算回归：手机 -> 拍照优先，预算4000，只返回 4000 元以内商品卡片
- [x] 上下文追问回归：推荐后问“第二个怎么样”会围绕上一轮第二个商品回答
- [x] 上下文价格回归：推荐后问“再便宜点”会追加低于上一轮候选的预算过滤
- [x] 商品对比回归：科颜氏 vs AHC 眼霜返回两侧商品卡和 `comparison_card`
- [x] 对比预算回归：小米 vs OPPO 拍照手机预算 4000 时，结论推荐预算内商品
- [x] 购物车回归：推荐商品后说“把刚才那款加到购物车”会返回 `cart_update`
- [x] Android Kotlin 编译验证：`:app:compileDebugKotlin`
- [x] AgentWorkflow 关键回归：澄清、LLM fallback、商品对比、上下文追问和购物车测试通过
- [x] SemanticPlanner 回归：`AHC 那个`、`那支来两件`、`科颜氏先不要了`、`比第二款更适合敏感肌但别太贵` 测试通过
- [x] Trace API 回归：`/debug/traces` 可返回最近一次 handler、plan 和结构化事件摘要
- [x] 运动鞋回归：`推荐一款运动鞋` 触发 `clothes.sports_shoes` 类型过滤，只返回鞋类商品，不返回运动裤
- [x] 离线评估回归：当前 `data/eval_queries.jsonl` 10/10 turns 通过

## 当前状态

最小闭环已经跑通：

```text
Android 真机 App
  -> OkHttp SSE
  -> adb reverse
  -> FastAPI /chat
  -> SemanticPlanner
  -> AgentWorkflow
  -> JSON/Chroma 商品检索
  -> Doubao-Seed grounded answer
  -> Agent trace / offline eval
  -> 流式 token + product_card + comparison_card + cart_update
  -> 手机端展示商品主图卡片、对比面板、购物车面板和详情弹窗
```

## 当前限制

- [ ] Ark/Doubao embedding 代码已接入，但默认关闭；需要 `USE_ARK_EMBEDDING=true` 并重新灌库后才走真实向量
- [ ] 真实 embedding 灌库尚未做端到端计费接口回归，当前自动化测试使用 mock，避免测试阶段触发外部调用
- [ ] 多轮对话已支持澄清主题补全、商品指代和轻量价格追问，但还不是完整长期记忆
- [ ] 购物车已支持本地模拟闭环，但尚未接真实支付、地址或订单系统
- [ ] 多模态仍是接口预留
- [ ] 商品详情页仍是本地模拟页，尚未接真实电商落地页

## 下一步

1. 按需打开 `USE_ARK_EMBEDDING=true` 做一次真实 embedding 灌库回归。
2. 继续完善 taxonomy 覆盖面，把更多商品类型、品牌和功效词沉淀为可配置元数据，并为 taxonomy 变更建立索引重灌/回归提醒。
3. 继续完善多轮查询改写，覆盖更多类目和偏好组合。
4. 扩充离线评估集，覆盖更多类目、失败样例、长链多轮和购物车边界条件。
5. 从 rerank、多模态、真实 embedding 灌库回归或 Demo 录屏中选择 1 个方向深入实现。
5. 做 Demo 脚本和答辩截图/录屏材料。
6. 后续如有真实商品落地页，再替换当前本地模拟页 URL。
