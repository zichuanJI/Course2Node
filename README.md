# Course2Note

将一节课的音频 + 幻灯片，自动生成结构化讲义笔记的 Research MVP。

## 核心流程

```
上传音频 / PPTX / PDF
    ↓
Extract   ASR 转录 + 幻灯片解析
    ↓
Align     转录文本与幻灯片单调对齐
    ↓
Retrieve  Minimax Agent 联网补充知识点（可选）
    ↓
Synthesize  旗舰 LLM 生成结构化 NoteDocument JSON
    ↓
Review    编辑 / Accept / Reject / 导出 MD · TeX · TXT
```

## 技术栈

| 层 | 技术 |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy (async) · Alembic |
| 任务队列 | Celery + Redis |
| 数据库 | PostgreSQL |
| 核心 LLM | Claude Opus 4 / Sonnet 4.6 · Gemini 2.5 Pro（可切换）|
| 检索 Agent | Minimax（轻量 tool-use 联网搜索）|
| 向量嵌入 | OpenAI text-embedding-3 |
| 搜索后端 | Tavily |
| Frontend | React 18 · Vite · TypeScript |

## 目录结构

```
Course2Note/
├── backend/
│   └── app/
│       ├── core/          # 规范类型 (types.py) + Provider 抽象接口
│       ├── api/routes/    # upload · sessions · export · review
│       ├── pipeline/      # 6 个 stage：ingest extract align retrieve synthesize export_renderer
│       ├── providers/     # LLM / Search / Embed / Minimax Agent 适配器
│       ├── workers/       # Celery app + tasks
│       ├── db/            # ORM models + async session
│       └── storage/       # 本地文件存储（dev）
├── frontend/
│   └── src/
│       ├── components/    # UploadForm · PipelineStatus · NoteEditor
│       ├── api/           # fetch 封装
│       └── types/         # TS 类型定义
├── artifacts/             # 运行时 artifact 存储根目录
└── docker-compose.yml
```

## 本地启动

**前提：** Docker Desktop 已运行。

```bash
# 1. 配置环境变量
cp .env.example .env
# 填入 ANTHROPIC_API_KEY / GOOGLE_API_KEY / MINIMAX_API_KEY / OPENAI_API_KEY / TAVILY_API_KEY

# 2. 启动全部服务
docker compose up

# 访问
# Frontend:  http://localhost:5173
# API docs:  http://localhost:8000/docs
```

不使用 Docker 时（纯本地）：

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Worker（新终端）
celery -A app.workers.celery_app worker --loglevel=info

# Frontend（新终端）
cd frontend
npm install
npm run dev
```

## 环境变量说明

| 变量 | 用途 |
|---|---|
| `SYNTHESIZE_LLM_PROVIDER` | `claude`（默认）或 `gemini` |
| `RETRIEVE_LLM_PROVIDER` | `minimax`（默认，用于联网检索 Agent）|
| `ANTHROPIC_API_KEY` | Claude 旗舰模型 |
| `GOOGLE_API_KEY` | Gemini 旗舰模型 |
| `MINIMAX_API_KEY` / `MINIMAX_GROUP_ID` | Minimax 检索 Agent |
| `OPENAI_API_KEY` | 向量嵌入 |
| `TAVILY_API_KEY` | 网络搜索 |

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/upload/` | 上传文件，创建会话，触发 pipeline |
| GET | `/sessions/` | 列出所有会话 |
| GET | `/sessions/{id}/status` | 轮询 pipeline 状态 |
| GET | `/export/{id}/{fmt}` | 导出笔记（`markdown` · `tex` · `txt`）|
| POST | `/review/{id}` | 提交块级编辑 / 评分事件 |

## 数据模型

核心类型定义见 `backend/app/core/types.py`，包括：

- **LectureSession** — 一次上传任务的完整状态
- **NoteDocument** — 结构化笔记 JSON（含 sections / supplemental\_context / key\_terms / open\_questions）
- **NoteBlock** — 最小笔记单元，携带 `provenance[]` 来源标注和 `grounding_level`
- **ReviewEvent** — 每次用户编辑/评分均持久化，供后续微调数据收集

## 开发状态

| Stage | 状态 |
|---|---|
| 工程骨架 + 类型定义 | ✅ 完成 |
| Stage 1 Ingest | 🔲 Stub |
| Stage 2 Extract（ASR / PPTX / PDF）| 🔲 Stub |
| Stage 3 Align（单调对齐）| 🔲 Stub |
| Stage 4 Retrieve（Minimax Agent）| 🔲 Stub |
| Stage 5 Synthesize（旗舰 LLM）| 🔲 Stub |
| Stage 6 Review & Export | 🔲 Stub |
