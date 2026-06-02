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
- [x] 已完成 Git 提交：`6dbb121`、`92751b5`
- [x] 严格关键词过滤：无严格匹配时降级说明，不返回无关商品
- [x] 一句话多重反选解析：如“不要含酒精的，也不要日系品牌”
- [x] Doubao/Ark LLM 客户端接入：`USE_LLM=true` 时基于 RAG 商品上下文生成回答
- [x] LLM 调用失败或未配置 API Key 时自动回退本地模板回答
- [x] 防幻觉 prompt：约束只基于候选商品回答，不编造价格、优惠、库存或功效
- [x] 从参考集 zip 抽取 100 张商品主图到 `data/product_images`
- [x] FastAPI 通过 `/assets/products/...` 提供商品主图静态资源

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
- [x] Android Debug 构建和真机安装成功

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

- [ ] Chroma 已接入，但当前 embedding 仍是本地 hashing embedding
- [ ] 还未接入 Doubao embedding
- [ ] 多轮对话目前是结构预留，尚未做完整查询改写
- [ ] 购物车、多模态、商品对比仍是接口预留
- [ ] `detail_url` 仍为空，当前通过 App 内详情弹窗展示商品信息

## 下一步

1. 接入 Doubao embedding，把本地 hashing embedding 替换为真实语义向量。
2. 完善多轮查询改写与主动澄清。
3. 给商品补齐本地详情页或模拟落地页 URL。
4. 从购物车、多模态、商品对比中选择 1-2 个加分项深入实现。
5. 做 Demo 脚本和答辩截图/录屏材料。
