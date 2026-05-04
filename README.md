# Course2Node

Course2Node 可以把课程 PDF、课件、笔记和音频转换成课堂演示用的知识点图谱。本项目是南京大学信息管理学院 数据科学与数据分析课程的小组项目，如果对你有所启发，**欢迎star！**

## 当前能力

- PDF 导入：通过 Kimi 文件抽取接口提取 PDF 文本；当前不渲染页面，也不保留页码定位。
- 音频导入：通过 Whisper 或 faster-whisper 转写课程音频。
- 文本切分：将抽取后的文本切成适合 embedding 和图谱抽取的 chunk。
- Embedding：默认使用本地 `BAAI/bge-m3`，也支持 OpenAI 或 OpenAI-compatible embedding 服务。
- 图谱抽取：使用兼容 OpenAI 的聊天模型抽取概念、属性、关系和 topic cluster；未配置 LLM 时会回退到规则 + 统计抽取。
- 搜索：对课程 chunk 和概念做关键词 + embedding 检索。
- 笔记与导出：基于图谱生成结构化笔记，并支持导出为 Markdown、TeX 或纯文本。
- 本地存储：session、上传文件、chunk、graph、notes、exam 等 artifact 以 JSON 形式存储在本地。
- 前端界面：Vite + React + TypeScript，提供上传流程、处理进度、知识图谱、搜索面板、概念详情和笔记视图。

## 处理流程

```text
上传 PDF/音频
  -> /ingest/pdf 或 /ingest/audio
  -> IngestArtifact (chunks)
  -> /build_graph
  -> GraphArtifact (concepts + edges + clusters)
  -> /generate_notes
  -> NoteDocument
  -> /export/{session_id}/{fmt}
  -> markdown / tex / txt
```

运行时 artifact 会写入：

```text
LOCAL_STORAGE_PATH/<session_id>/
```

当前 MVP 使用本地 JSON artifact，不依赖 Neo4j 或数据库。`backend/app/db/`、`backend/app/pipeline/`、`backend/app/workers/` 属于下一阶段代码，目前未接入主流程。

## 仓库结构

```text
backend/
  app/
    api/routes/                 FastAPI 路由：upload、sessions、graph、export、settings
    core/types.py               Pydantic 数据模型定义
    providers/                  LLM、embedding、search provider 适配器
    services/
      ingestion.py              PDF/音频 ingest，生成 chunk 和 embedding
      kimi_pdf.py               Kimi PDF 文本抽取
      embeddings.py             embedding provider 调度
      llm_graph.py              LLM 图谱抽取 prompt 与 JSON 解析
      graph_builder.py          概念、关系、cluster、centrality 构建
      search.py                 关键词 + embedding 搜索
      notes.py                  笔记生成
      exam.py                   试题/练习生成
    storage/local.py            本地 JSON artifact 持久化
  tests/                        后端测试
frontend/
  src/
    api/client.ts               前端 API client
    pages/                      Home、NewSession、Pipeline、Workspace 页面
    components/graph/           ReactFlow 图谱与布局
    components/search/          搜索面板
    components/notes/           Markdown 笔记渲染
    styles/theme.css            CSS 设计 token 和主题
artifacts/                      本地运行时数据，默认被 git 忽略
docker-compose.yml              可选的本地 Docker 双服务栈
```

## 核心实现说明

- `backend/app/core/types.py` 是所有数据结构的统一来源，例如 `CourseSession`、`IngestArtifact`、`GraphArtifact`、`ConceptNode`、`GraphEdge`、`NoteDocument`。
- `backend/app/storage/local.py` 负责所有 artifact 的 load/save；业务代码不应绕过它直接读写 artifact。
- `backend/app/services/ingestion.py` 负责 PDF 和音频导入，并把内容转为 chunk。
- `backend/app/services/kimi_pdf.py` 负责调用 Kimi 抽取 PDF 文本。
- `backend/app/services/embeddings.py` 根据 `EMBED_PROVIDER` 选择本地 BGE-M3、OpenAI 或 OpenAI-compatible embedding。
- `backend/app/services/llm_graph.py` 包含图谱抽取的 system prompt 和 LLM JSON 解析。
- `backend/app/services/graph_builder.py` 负责清洗概念、构建关系、计算 degree / weighted degree / betweenness / closeness 等中心性，并生成 topic cluster。
- `frontend/src/components/graph/ConceptGraph.tsx` 和 `layoutUtils.ts` 负责图谱渲染和 `force`、`radial`、`cluster` 三种布局。
- `frontend/src/components/graph/ConceptDrawer.tsx` 负责概念详情抽屉，包括定义、统计、证据和邻居节点。

## 运行环境要求

- Python 3.11 或 3.12
- Node.js 20+ 或 22+
- `ffmpeg`，用于音频转换和 Whisper 转写
- 首次使用本地 `BAAI/bge-m3` 或 Whisper 模型时需要网络下载模型权重
- Kimi API key，用于 PDF 文本抽取
- 图谱 LLM API key，用于高质量概念和关系抽取

### 安装 ffmpeg

macOS：

```bash
brew install ffmpeg
```

Windows：

```powershell
winget install Gyan.FFmpeg
```

安装后重新打开终端，并确认：

```powershell
ffmpeg -version
```

## 配置环境变量

从示例文件复制一份 `.env`：

macOS / Linux：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

不要提交 `.env` 或真实 API key。后端会从仓库根目录读取 `.env`。

### 核心配置

| 变量                         | 是否必需    | 用途                                                                  |
| ---------------------------- | ----------- | --------------------------------------------------------------------- |
| `LOCAL_STORAGE_PATH`         | 是          | artifact 存储目录。本地开发建议用绝对路径；Docker 使用 `/artifacts`。 |
| `GRAPH_LLM_BASE_URL`         | 是          | 兼容 OpenAI 的聊天 API base URL，例如 `https://api.deepseek.com/v1`。 |
| `GRAPH_LLM_API_KEY`          | 是          | 图谱抽取模型 API key。                                                |
| `GRAPH_LLM_MODEL`            | 是          | 图谱抽取模型名，例如 `deepseek-chat`。                                |
| `KIMI_BASE_URL`              | 是          | Kimi base URL，通常为 `https://api.moonshot.cn/v1`。                  |
| `KIMI_API_KEY`               | PDF 必需    | PDF 文本抽取使用的 Kimi API key。                                     |
| `KIMI_MODEL`                 | PDF 必需    | Kimi 模型名，当前默认 `kimi-k2.6`。                                   |
| `EMBED_PROVIDER`             | 是          | `bge_m3`、`openai` 或 `openai_compatible`。                           |
| `EMBEDDING_LOCAL_MODEL_NAME` | bge-m3 必需 | 本地 embedding 模型，默认 `BAAI/bge-m3`。                             |
| `WHISPER_MODEL_SIZE`         | 音频必需    | Whisper 模型大小，例如 `base`、`small`、`medium`。                    |
| `WHISPER_LANGUAGE`           | 可选        | 默认 `auto`；识别不稳定时可设置 `zh` 或 `en`。                        |
| `VITE_API_BASE_URL`          | 可选        | 前端 API base URL。默认 `http://localhost:8000`。                     |

推荐的本地 `.env` 示例：

```bash
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./artifacts

GRAPH_LLM_BASE_URL=https://api.deepseek.com/v1
GRAPH_LLM_API_KEY=sk-your-graph-llm-key
GRAPH_LLM_MODEL=deepseek-chat
GRAPH_LLM_TIMEOUT_SECONDS=90

KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_API_KEY=sk-your-kimi-key
KIMI_MODEL=kimi-k2.6
KIMI_TIMEOUT_SECONDS=90

EMBED_PROVIDER=bge_m3
EMBEDDING_LOCAL_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_DEVICE=cpu
EMBEDDING_LOCAL_USE_FP16=false

WHISPER_MODEL_SIZE=base
WHISPER_LANGUAGE=auto
```

如果使用 OpenAI-compatible embedding 服务：

```bash
EMBED_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-provider/v1
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_MODEL=your-embedding-model
```

## 本地启动

建议分别启动后端和前端。

### 后端：macOS / Linux

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.venv/bin/python -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 后端：Windows PowerShell

使用阿里云而不是清华源，因为我连不上清华源

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip wheel packaging "setuptools==69.5.1" -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com; .\.venv\Scripts\python.exe -m pip install -r requirements.txt --no-build-isolation -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

如果 `openai-whisper` 构建时报 `No module named 'pkg_resources'`，使用上面这一行安装命令。它会先固定 `setuptools==69.5.1`，再关闭 build isolation 安装 `requirements.txt`。

### 前端：macOS / Linux / Windows

在另一个终端中运行：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Windows PowerShell 下，`npm run dev -- --host ...` 可能会被 npm 解析错。Windows 使用：

```bash
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173
```

如果后端不是 `http://localhost:8000`，创建 `frontend/.env.local`：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

启动后打开：

- 前端：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## Docker 启动

Docker 适合准备干净的演示环境。启动前在 `.env` 中设置：

```bash
LOCAL_STORAGE_PATH=/artifacts
```

然后运行：

```bash
docker compose up --build
```

Docker 暴露的端口：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 测试与检查

### 后端测试

macOS / Linux：

```bash
cd backend
.venv/bin/python -m pytest
```

Windows PowerShell：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

### 后端语法检查

macOS / Linux：

```bash
cd backend
.venv/bin/python -m compileall app tests
```

Windows PowerShell：

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app tests
```

### 前端生产构建

```bash
cd frontend
npm run build
```

## 常见修改位置

- PDF 抽取逻辑：`backend/app/services/kimi_pdf.py`
- 音频转写逻辑：`backend/app/services/ingestion.py`
- chunk 切分和规则抽取：`backend/app/services/text_utils.py`
- embedding provider：`backend/app/services/embeddings.py`、`backend/app/providers/embed/local_bge_m3.py`
- 图谱抽取 prompt：`backend/app/services/llm_graph.py`
- 图谱清洗、关系和中心性计算：`backend/app/services/graph_builder.py`
- 搜索逻辑：`backend/app/services/search.py`
- 笔记生成：`backend/app/services/notes.py`
- 试题生成：`backend/app/services/exam.py`
- 图谱渲染和布局：`frontend/src/components/graph/ConceptGraph.tsx`、`frontend/src/components/graph/layoutUtils.ts`
- 前端 API 调用：`frontend/src/api/client.ts`
- 主题和设计 token：`frontend/src/styles/theme.css`

## 故障排查

- `python3` 在 Windows 上失败：Windows 通常使用 `python` 或 `py`，不要直接照抄 macOS/Linux 的 `python3` 命令。
- `Kimi PDF extraction is not configured`：检查 `KIMI_API_KEY` 和 `KIMI_MODEL`。
- `LLM graph extraction returned no valid concepts`：检查 `GRAPH_LLM_*`，确认 ingest 是否生成了有效 chunk；必要时增大 `GRAPH_LLM_TIMEOUT_SECONDS`。
- `ASR failed`：确认已安装 `ffmpeg`，并确认后端 venv 中已安装 `faster-whisper` 或 `openai-whisper`；也可以尝试更小的 `WHISPER_MODEL_SIZE`。
- 首次运行很慢：本地 BGE-M3 和 Whisper 可能会下载模型权重，并在 CPU 上初始化。
- 重启后旧课程消失：使用稳定的绝对路径 `LOCAL_STORAGE_PATH`。
- PowerShell 提示无法加载 `Microsoft.PowerShell_profile.ps1`：这是本机 PowerShell 执行策略问题，通常不影响项目命令运行。

## CORS

开发环境中，后端 CORS 在 `backend/app/main.py` 里设置为 `allow_origins=["*"]`。生产部署前应收紧此配置。
