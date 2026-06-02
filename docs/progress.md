# 项目进度

更新时间：2026-06-02

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
- [x] 预算解析增强：支持“预算4000”这类预算前置表达，并继续由程序化价格过滤执行
- [x] 商品对比：识别“X 和 Y / X vs Y / X 与 Y”，分别检索双方候选并返回 `comparison_card`
- [x] 对比预算处理：对比时保留双方候选解释差异，推荐结论优先选择预算内商品

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
- [x] 商品对比回归：科颜氏 vs AHC 眼霜返回两侧商品卡和 `comparison_card`
- [x] 对比预算回归：小米 vs OPPO 拍照手机预算 4000 时，结论推荐预算内商品

## 当前状态

最小闭环已经跑通：

```text
Android 真机 App
  -> OkHttp SSE
  -> adb reverse
  -> FastAPI /chat
  -> JSON/Chroma 商品检索
  -> Doubao-Seed grounded answer
  -> 流式 token + product_card
  -> 手机端展示商品主图卡片和详情弹窗
```

## 当前限制

- [ ] Ark/Doubao embedding 代码已接入，但默认关闭；需要 `USE_ARK_EMBEDDING=true` 并重新灌库后才走真实向量
- [ ] 真实 embedding 灌库尚未做端到端计费接口回归，当前自动化测试使用 mock，避免测试阶段触发外部调用
- [ ] 多轮对话已支持澄清主题补全，但还不是完整 LLM 查询改写/长期记忆
- [ ] 商品对比后端已实现，但 Android 端暂未单独渲染 `comparison_card`，当前通过文本回答和商品卡片演示
- [ ] 购物车、多模态仍是接口预留
- [ ] 商品详情页仍是本地模拟页，尚未接真实电商落地页

## 下一步

1. 按需打开 `USE_ARK_EMBEDDING=true` 做一次真实 embedding 灌库回归。
2. 继续完善多轮查询改写，覆盖更多类目和偏好组合。
3. 在 Android 端渲染 `comparison_card`，或从购物车、多模态中选择 1 个加分项深入实现。
4. 做 Demo 脚本和答辩截图/录屏材料。
5. 后续如有真实商品落地页，再替换当前本地模拟页 URL。
