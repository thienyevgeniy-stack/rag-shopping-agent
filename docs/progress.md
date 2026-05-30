# 项目进度

更新时间：2026-05-30

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

## 当前状态

最小闭环已经跑通：

```text
Android 真机 App
  -> OkHttp SSE
  -> adb reverse
  -> FastAPI /chat
  -> JSON/Chroma 商品检索
  -> 流式 token + product_card
  -> 手机端展示商品结果
```

## 当前限制

- [ ] Chroma 已接入，但当前 embedding 仍是本地 hashing embedding
- [ ] 还未接入 Doubao embedding
- [ ] 还未接入 Doubao-Seed 生成回答
- [ ] 多轮对话目前是结构预留，尚未做完整查询改写
- [ ] 购物车、多模态、商品对比仍是接口预留
- [ ] Android 商品卡片暂未渲染主图，`detail_url` 仍为空时无法真实跳转落地页

## 下一步

1. 接入 Doubao embedding，把本地 hashing embedding 替换为真实语义向量。
2. 接入 Doubao-Seed 生成回答，继续严格使用检索上下文防幻觉。
3. 完善多轮查询改写与主动澄清。
4. 在 Android 商品卡片中渲染主图，并补齐可点击落地页。
5. 从购物车、多模态、商品对比中选择 1-2 个加分项深入实现。
