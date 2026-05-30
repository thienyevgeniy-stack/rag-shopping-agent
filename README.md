# RAG 多模态电商智能导购 Agent

本仓库用于课题 Demo：用原生 Android 客户端、FastAPI 后端和 RAG 检索链路，构建一个可流式对话、可展示商品卡片的电商导购 Agent。

## 当前状态

- 已搭建 monorepo 结构：`client/`、`server/`、`docs/`、`data/`、`scripts/`
- 后端提供 `/health` 和 `/chat` SSE 接口
- 后端内置本地 JSON 商品检索 fallback，后续可替换为 Chroma
- Android 端已预留 Compose 对话页、SSE 客户端、商品卡片模型
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

启用 Chroma：

```powershell
$env:USE_CHROMA="true"
.\scripts\run_server.ps1
```

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

## 开发优先级

1. 跑通最小闭环：Android 输入 → FastAPI → 检索 → SSE 回复 → 商品卡片
2. 接入真实 embedding / Chroma / Doubao 生成
3. 做深多轮上下文与反选排除
4. 预留购物车、多模态、对比决策接口

详细设计见 [docs/architecture.md](docs/architecture.md)、[docs/api.md](docs/api.md) 和 [docs/progress.md](docs/progress.md)。

Android 构建与联调见 [docs/android_setup.md](docs/android_setup.md)。
