# RAG 多模态电商智能导购 Agent

本仓库用于课题 Demo：用原生 Android 客户端、FastAPI 后端和 RAG 检索链路，构建一个可流式对话、可展示商品卡片的电商导购 Agent。

## 评委快速体验

完整部署、后端体验、Android 真机联调和常见问题见 [docs/deployment_and_demo.md](docs/deployment_and_demo.md)。

最短本地后端启动：

```powershell
git clone https://github.com/thienyevgeniy-stack/rag-shopping-agent.git
cd rag-shopping-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r server\requirements.txt
copy .env.example .env
.\scripts\run_server.ps1
```

推荐使用 Python 3.11 或 3.12。Windows 上不建议使用 Python 3.13 / 3.14，否则部分原生依赖可能触发本地编译并报 `link.exe not found`。完整说明见 [docs/deployment_and_demo.md](docs/deployment_and_demo.md)。

启动后打开：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/admin
```

Android 真机演示时，保持后端运行，并执行：

```powershell
adb reverse tcp:8000 tcp:8000
```

然后在 Android Studio 打开 `client/` 并运行 `app`。

## 当前状态

- 已搭建 monorepo 结构：`client/`、`server/`、`docs/`、`data/`、`scripts/`
- 后端提供 `/health` 和 `/chat` SSE 接口
- 后端支持本地 JSON 商品检索 fallback，也可通过 `USE_CHROMA=true` 启用 Chroma
- 后端可通过 `USE_LLM=true` 接入 Doubao/Ark 生成回答，失败时自动回退模板回答
- 后端提供 `GroundingGuard` 回答后校验：拦截未提供的优惠/库存/销量、候选外价格和高风险绝对化功效，并自动降级为 grounded 模板回答
- Chroma 默认使用本地 hashing embedding；可通过 `USE_ARK_EMBEDDING=true` 切换到 Ark/Doubao embedding
- 检索层支持 `product_type` 和价格 metadata 预过滤；Chroma 会使用 metadata `where` 下推，本地 JSON fallback 会使用商品类型倒排索引和文档特征缓存
- 后端支持主动澄清：宽泛需求会先追问预算/偏好，再进入检索
- 后端支持基础上下文追问：可处理“第二个怎么样”“再便宜点”等跟进表达
- 后端支持商品对比：识别品牌/商品对，返回对比回答、商品卡片和 `comparison_card`
- 后端支持对话式购物车：可加购、查看、删除、修改数量并返回 `cart_update`
- 后端支持结构化语义规划：LLM JSON plan + Pydantic 校验 + 规则 fallback，减少对固定句式的依赖
- 后端支持可配置商品 taxonomy：将“运动鞋/跑鞋/跑步的鞋/运动裤/手机”等归一为标准 `product_type`，作为检索前 facet 过滤条件
- 后端支持商品范围切换时清理旧过滤条件，避免长会话中旧品类、旧预算污染新需求
- 后端支持轻量多模态找货：Android 可附加图片，后端用商品主图视觉签名做相似匹配，再进入同一 RAG 检索流程
- 后端支持场景化组合推荐：如“三亚度假/通勤/运动训练”会拆成多个商品槽位并跨类目返回组合方案
- 后端加入首 Token 延迟压测脚本，推荐和组合链路会先发即时 token，降低用户等待感
- 后端智能体已拆为轻量 `AgentWorkflow`：澄清、购物车、对比、上下文追问和普通推荐分别由 handler 承接
- 后端提供 Agent trace 和离线评估脚本，支持定位 planner、handler、检索和购物车链路问题
- 后端通过 `/assets/products/...` 提供商品主图静态资源
- 后端通过 `/products/{id}` 提供本地商品详情页
- Android 端已实现 Compose 对话页、SSE 客户端、商品主图卡片、对比面板、购物车面板、详情弹窗和落地页跳转
- 真实 API Key 通过 `.env` 管理，不进入 Git

## 目录结构

```text
.
├── client/                  # Android Kotlin + Jetpack Compose
├── server/                  # FastAPI 后端与 RAG/Agent 模块
├── data/                    # 示例商品数据
├── docs/                    # 架构、接口、部署体验文档
├── scripts/                 # 本地启动脚本
├── .env.example             # 环境变量示例
└── README.md
```

## 后端快速启动

```powershell
cd <repo>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
copy .env.example .env
.\scripts\run_server.ps1
```

后端测试：

```powershell
cd <repo>
.\scripts\test_backend.ps1
```

离线评估：

```powershell
cd <repo>
python scripts\evaluate_agent.py
```

检索性能压测：

```powershell
cd <repo>
python scripts\benchmark_retrieval.py --store local --sizes 50000 --runs 1 --warmup 1 --top-k 5 --output docs\retrieval_benchmark_2026-06-07-local-50k-r1.json
python scripts\benchmark_retrieval.py --store chroma --sizes 1000 --runs 1 --warmup 0 --top-k 5 --output docs\retrieval_benchmark_2026-06-07-chroma-1k.json
```

首 Token 延迟压测：

```powershell
cd <repo>
python scripts\benchmark_first_token.py --url http://127.0.0.1:8000/chat --runs 3 --warmup 1 --threshold-ms 1000 --output docs\first_token_benchmark_2026-06-07.json
```

查看最近对话 trace：

```powershell
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/debug/traces?limit=5"
```

灌入 Chroma 向量库（可选；未启用时默认使用 JSON fallback）：

```powershell
cd <repo>
pip install -r server\requirements.txt
python -m server.rag.ingest
```

抽取参考集商品主图：

```powershell
cd <repo>
python scripts\extract_ref_images.py
```

启用 Chroma：

```powershell
$env:USE_CHROMA="true"
.\scripts\run_server.ps1
```

启用 Ark/Doubao embedding 后重新灌库：

```powershell
# 先在 .env 中填入 ARK_API_KEY，不要提交 .env
$env:USE_CHROMA="true"
$env:USE_ARK_EMBEDDING="true"
$env:ARK_EMBEDDING_MODEL="doubao-embedding-text-240515"
$env:EMBEDDING_BATCH_SIZE="4"
python -m server.rag.ingest
.\scripts\run_server.ps1
```

启用 Doubao/Ark 生成回答：

```powershell
# 先在 .env 中填入 ARK_API_KEY，不要提交 .env
$env:USE_LLM="true"
.\scripts\run_server.ps1
```

如果未配置 `ARK_API_KEY` 或模型调用失败，后端会自动回退到本地模板回答，`/chat` 不会因此中断。

生产/部署相关开关：

```powershell
# development 默认开启 /debug；production 默认关闭 /debug
$env:APP_ENV="production"
$env:CORS_ALLOWED_ORIGINS="https://your-web.example.com"
$env:CORS_ALLOW_CREDENTIALS="false"
$env:SESSION_BACKEND="sqlite"
$env:SESSION_DB_PATH="server/runtime/sessions.sqlite3"
$env:SESSION_REDIS_URL="redis://localhost:6379/0"
$env:SESSION_TTL_SECONDS="43200"
$env:SESSION_MAX_ITEMS="500"
$env:TRACE_MAX_ITEMS="200"
.\scripts\run_server.ps1
```

如需在非生产环境强制开关调试接口，可设置 `ENABLE_DEBUG_API=true|false`。生产部署不要使用通配 CORS，也不要对公网开放 `/debug`。

`SESSION_BACKEND=memory` 适合本地临时调试；`SESSION_BACKEND=sqlite` 会把会话、候选商品和购物车持久化到 `SESSION_DB_PATH`，服务重启后同一 `session_id` 可恢复购物车状态。SQLite 文件属于运行时数据，已被 `.gitignore` 排除。多实例生产部署可设置 `SESSION_BACKEND=redis` 和 `SESSION_REDIS_URL`，让多个后端进程共享会话与购物车状态。

启用 LLM 语义规划（可选，默认关闭以保证演示延迟稳定）：

```powershell
$env:USE_SEMANTIC_LLM="true"
$env:SEMANTIC_LLM_BUDGET_SECONDS="0.25"
.\scripts\run_server.ps1
```

语义 LLM 只负责输出结构化 plan；超出预算会回退规则解析。Planner 只读取压缩后的会话上下文，输出还会经过 `PlannerPolicy` 校验：缺少确定性证据的加购、删除、改数量、结算等购物车写操作会被改为澄清，不会直接修改状态。推荐回答的首屏路径仍由 `RECOMMENDATION_LLM_BUDGET_SECONDS` 控制，可设为 `0` 以优先保证首屏速度。

查询规划回归评测：

```powershell
python scripts\evaluate_query_plans.py
```

该脚本读取 `server/eval/query_plan_cases.json`，检查 intent、route、品类、预算、否定和引用解析。`known_gap` 用例会单独报告但不让本地回归失败。

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

SSE 对话测试：

```powershell
$body = @{
  session_id = "demo"
  message = "推荐一款保湿眼霜，预算250以内"
} | ConvertTo-Json -Compress

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

## 当前开发重点

1. 已跑通最小闭环：Android 输入 → FastAPI → 检索 → Doubao/模板生成 → SSE 回复 → 商品主图卡片 → 商品详情页
2. 已接入 Chroma 持久化链路、Ark/Doubao embedding 适配和 Doubao/Ark 回答生成
3. 已实现基础主动澄清、澄清主题补全、上下文追问、商品对比、端侧对比面板、对话式购物车、图片找货入口和场景化组合推荐，并完成后端智能体工作流和语义规划层拆分
4. 已加入商品 taxonomy/facet 过滤、商品范围状态清理、Agent trace 和离线评估样例，用于持续检查 planner、handler、商品命中和购物车行为
5. 已加入大库检索压测脚本、首 Token 压测脚本、本地 fallback 倒排索引/特征缓存、Chroma metadata where 下推和压测报告；下一步从真实 Chroma embedding 灌库回归、rerank、评估集扩充和 Demo 录屏中选择 1-2 个方向深入完善

详细设计见 [docs/architecture.md](docs/architecture.md)、[docs/rag_product_maturity.md](docs/rag_product_maturity.md)、[docs/retrieval_benchmark_2026-06-07.md](docs/retrieval_benchmark_2026-06-07.md)、[docs/first_token_benchmark_2026-06-07.md](docs/first_token_benchmark_2026-06-07.md)、[docs/api.md](docs/api.md) 和 [docs/progress.md](docs/progress.md)。

Android 构建与联调见 [docs/android_setup.md](docs/android_setup.md)。
