# 部署与评委快速体验指南

本文面向评委、助教和协作开发者，说明如何从公开 GitHub 仓库快速运行本项目，并完成“客户端 App + 后端服务”的端到端体验。

项目仓库：

```text
https://github.com/thienyevgeniy-stack/rag-shopping-agent
```

## 1. 体验方式总览

推荐优先使用本地真机演示方式：

```text
Android 真机 App
  -> adb reverse tcp:8000 tcp:8000
  -> 本机 FastAPI 后端 http://127.0.0.1:8000
  -> RAG 检索 / Agent 工作流 / 商品卡片 / 购物车
```

如果没有 Android 真机，也可以先只体验后端：

- 健康检查：`http://127.0.0.1:8000/health`
- 后台面板：`http://127.0.0.1:8000/admin`
- SSE 对话接口：`POST http://127.0.0.1:8000/chat`

说明：

- `.env` 不进入 Git，评委本地按 `.env.example` 创建即可。
- 不配置 API Key 也能演示，系统会使用本地 JSON 商品库和模板/规则 fallback。
- 如需体验 Doubao/Ark LLM 或 embedding，请在本地 `.env` 中自行填写 `ARK_API_KEY`。

## 2. 环境要求

后端：

- Windows 10/11、macOS 或 Linux
- Python 3.10+
- Git

Android 客户端：

- Android Studio
- JDK 17+
- Android SDK Platform 35
- 一台已开启 USB 调试的 Android 手机，或 Android 模拟器

可选：

- Redis，用于验证 Redis 会话后端
- Chroma，用于向量库持久化路径
- Doubao/Ark API Key，用于真实 LLM / embedding 调用

## 3. 获取代码

```powershell
git clone https://github.com/thienyevgeniy-stack/rag-shopping-agent.git
cd rag-shopping-agent
```

后续命令均假设当前目录是仓库根目录，文档中用 `<repo>` 表示该目录。

## 4. 后端快速启动

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r server\requirements.txt
Copy-Item .env.example .env
.\scripts\run_server.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r server/requirements.txt
cp .env.example .env
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后打开：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/admin
```

预期 `/health` 返回：

```json
{
  "status": "ok",
  "env": "development"
}
```

## 5. 后端接口快速体验

PowerShell：

```powershell
$body = @{
  session_id = "judge-demo"
  message = "推荐一款1000元以上的运动鞋"
} | ConvertTo-Json -Compress

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

也可以在 Admin Console 观察：

- 服务健康状态
- Taxonomy 覆盖率
- Query failure 统计
- 最近请求 Trace
- Handler 分布

Admin Console 是开发/评审辅助面板，不建议在公网生产环境无鉴权开放。

## 6. Android 真机端到端体验

1. 保持后端运行在电脑本机 `127.0.0.1:8000`。

2. 连接 Android 手机并确认 ADB 可见：

```powershell
adb devices -l
```

如果 `adb` 不在 PATH，可使用 Android SDK 路径，例如：

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices -l
```

3. 开启 USB 反向代理：

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse --list
```

预期能看到：

```text
tcp:8000 tcp:8000
```

4. 在 Android Studio 打开：

```text
<repo>/client
```

等待 Gradle Sync 完成后，选择手机运行 `app`。

也可以命令行构建：

```powershell
cd client
.\gradlew.bat :app:assembleDebug
.\gradlew.bat :app:installDebug
```

5. 打开手机 App，输入以下问题体验：

```text
推荐一款1000元以上的运动鞋
推荐一款欧莱雅的口红
推荐一套三亚的旅行装备
把第一款加入购物车
把数量改成2
不要刚才那个品牌
```

评委应能看到：

- 流式回复
- 商品卡片
- 商品详情弹窗
- 购物车数量更新
- 历史对话 / 新建对话
- 后端 Admin Console 中对应 trace

## 7. Android 模拟器或远程服务器

物理真机推荐 `adb reverse`，App 默认访问：

```text
http://127.0.0.1:8000
```

模拟器访问电脑本机时，应改为：

```text
http://10.0.2.2:8000
```

当前客户端地址位于：

```text
client/app/src/main/java/com/example/ragshoppingagent/network/BackendConfig.kt
```

如需连接云服务器，请将 `LOCAL_REVERSE_PROXY_BASE_URL` 改为服务器地址，例如：

```kotlin
const val LOCAL_REVERSE_PROXY_BASE_URL = "https://your-domain.example.com"
```

然后重新构建安装 App。

## 8. 服务器部署说明

最小服务器部署命令：

```bash
git clone https://github.com/thienyevgeniy-stack/rag-shopping-agent.git
cd rag-shopping-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
cp .env.example .env
```

编辑 `.env`，生产/公网建议至少设置：

```env
APP_ENV=production
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
ENABLE_DEBUG_API=false
ENABLE_ADMIN_CONSOLE=false
CORS_ALLOWED_ORIGINS=https://your-frontend.example.com
CORS_ALLOW_CREDENTIALS=false
SESSION_BACKEND=sqlite
PUBLIC_BASE_URL=https://your-domain.example.com
```

启动：

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

如果使用 Nginx / HTTPS，建议由 Nginx 终止 TLS，再反向代理到本机 `8000` 端口。

生产注意事项：

- 不要提交 `.env`。
- 不要把 `ARK_API_KEY` 写入 README 或源码。
- 不要公网开放 `/debug`。
- Admin Console 当前适合本地/内网评审，不建议无鉴权公网开放。
- `server/runtime/`、`server/chroma_db/`、`data_external/` 是运行时或外部数据目录，已被 `.gitignore` 排除。

## 9. 可选能力开关

本地无 Key 体验：

```env
USE_LLM=false
USE_CHROMA=false
USE_ARK_EMBEDDING=false
```

启用 LLM：

```env
USE_LLM=true
ARK_API_KEY=your_key_here
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=your_model_or_endpoint
```

启用语义 Planner：

```env
USE_SEMANTIC_LLM=true
SEMANTIC_LLM_BUDGET_SECONDS=0.25
```

启用 Chroma：

```env
USE_CHROMA=true
CHROMA_DIR=server/chroma_db
```

启用 Redis 会话：

```env
SESSION_BACKEND=redis
SESSION_REDIS_URL=redis://localhost:6379/0
```

## 10. 验证与回归测试

后端全量测试：

```powershell
python -m pytest server/tests -q
```

查询规划评测：

```powershell
python scripts\evaluate_query_plans.py
```

Taxonomy 评测：

```powershell
python scripts\evaluate_taxonomy.py
```

首屏延迟压测：

```powershell
python scripts\benchmark_first_token.py --url http://127.0.0.1:8000/chat --runs 3 --warmup 1 --threshold-ms 1000
```

## 11. 常见问题

### 手机提示 fail to connect 127.0.0.1:8000

通常是 ADB reverse 没开：

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse --list
```

同时确认后端正在监听：

```powershell
curl http://127.0.0.1:8000/health
```

### GitHub 上看到历史本机路径

固定盘符形式的路径是开发机本地路径。公开文档中应使用 `<repo>` 或仓库根目录描述；测试里的 `http://127.0.0.1:8000` 是本地服务地址，属于正常演示配置，不需要改。

### 没有 API Key 是否能演示

可以。默认 `.env.example` 中 `USE_LLM=false`、`USE_CHROMA=false`，后端会使用本地商品 JSON 和规则/模板 fallback 完成基本导购闭环。

### Admin Console 为什么生产默认关闭

Admin Console 会展示 trace、query failure、taxonomy 统计和本地配置摘要。它适合开发和评审，不适合无鉴权公网开放。
