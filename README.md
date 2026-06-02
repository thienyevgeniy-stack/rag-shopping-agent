# RAG 多模态电商智能导购 Agent

本仓库用于课题 Demo：用原生 Android 客户端、FastAPI 后端和 RAG 检索链路，构建一个可流式对话、可展示商品卡片的电商导购 Agent。

## 当前状态

- 已搭建 monorepo 结构：`client/`、`server/`、`docs/`、`data/`、`scripts/`
- 后端提供 `/health` 和 `/chat` SSE 接口
- 后端支持本地 JSON 商品检索 fallback，也可通过 `USE_CHROMA=true` 启用 Chroma
- 后端可通过 `USE_LLM=true` 接入 Doubao/Ark 生成回答，失败时自动回退模板回答
- Chroma 默认使用本地 hashing embedding；可通过 `USE_ARK_EMBEDDING=true` 切换到 Ark/Doubao embedding
- 后端支持主动澄清：宽泛需求会先追问预算/偏好，再进入检索
- 后端支持商品对比：识别品牌/商品对，返回对比回答、商品卡片和 `comparison_card`
- 后端通过 `/assets/products/...` 提供商品主图静态资源
- 后端通过 `/products/{id}` 提供本地商品详情页
- Android 端已实现 Compose 对话页、SSE 客户端、商品主图卡片、详情弹窗和落地页跳转
- 真实 API Key 通过 `.env` 管理，不进入 Git

## 目录结构

```text
.
├── client/                  # Android Kotlin + Jetpack Compose
├── server/                  # FastAPI 后端与 RAG/Agent 模块
├── data/                    # 示例商品数据
├── docs/                    # 架构、接口、演示脚本
├── scripts/                 # 本地启动脚本
├── .env.example             # 环境变量示例
└── README.md
```

## 后端快速启动

```powershell
cd D:\RAG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
copy .env.example .env
.\scripts\run_server.ps1
```

后端测试：

```powershell
cd D:\RAG
.\scripts\test_backend.ps1
```

灌入 Chroma 向量库（可选；未启用时默认使用 JSON fallback）：

```powershell
cd D:\RAG
pip install -r server\requirements.txt
python -m server.rag.ingest
```

抽取参考集商品主图：

```powershell
cd D:\RAG
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
3. 已实现基础主动澄清、澄清主题补全和商品对比
4. 下一步从购物车、多模态、端侧对比卡渲染中选择 1-2 个加分项深入实现

详细设计见 [docs/architecture.md](docs/architecture.md)、[docs/api.md](docs/api.md) 和 [docs/progress.md](docs/progress.md)。

Android 构建与联调见 [docs/android_setup.md](docs/android_setup.md)。
