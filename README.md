# Course2Node

把课程 `PDF + 音频` 转成“每个节点都是知识点”的图谱式课程理解系统。

## V1 定位

- 主图中的每个节点都是 `知识点`
- PDF 页码和音频时间戳不做主图节点，只作为知识点的 `evidence_refs`
- 主图边只保留知识点之间的关系：
  - `RELATES_TO`
  - `CO_OCCURS_WITH`
  - `CONTAINS`（主题簇到知识点）
- 当前实现默认使用本地 JSON artifact 持久化，方便课程项目直接启动和演示

## 数据流

```text
上传 PDF / 音频
  -> ingest/pdf + ingest/audio
  -> 统一证据块（chunk）抽取
  -> LLM 知识点抽取 / 规则清洗 / 关系构图
  -> 构建知识点图谱
  -> 搜索知识点 / 查看子图
  -> 生成结构化笔记
  -> 导出 markdown / txt / tex
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/sessions/` | 列出已有 session |
| GET | `/sessions/{session_id}` | 获取 session 详情 |
| GET | `/sessions/{session_id}/status` | 获取 session 状态与统计 |
| POST | `/upload/pdf` | 上传 PDF |
| POST | `/upload/audio` | 上传音频 |
| POST | `/upload/pdfs` | 批量上传 PDF，可选自动 ingest + build |
| POST | `/ingest/pdf` | 解析 PDF，生成证据块 |
| POST | `/ingest/audio` | 转写音频，生成证据块 |
| POST | `/build_graph` | 构建知识点主图 |
| POST | `/search` | 搜索知识点与证据片段 |
| GET | `/graph/subgraph` | 查看某个知识点的局部关系图 |
| GET | `/graph/{session_id}` | 获取完整 graph artifact |
| POST | `/generate_notes` | 根据主题生成结构化笔记 |
| GET | `/notes/{session_id}` | 获取生成后的笔记 JSON |
| GET | `/export/{session_id}/{fmt}` | 导出 `markdown/txt/tex` |

## 后端结构

```text
backend/app/
├── api/routes/
│   ├── upload.py
│   ├── sessions.py
│   ├── graph.py
│   └── export.py
├── services/
│   ├── ingestion.py
│   ├── graph_builder.py
│   ├── search.py
│   ├── notes.py
│   └── text_utils.py
├── core/types.py
├── storage/local.py
└── main.py
```

当前真正启用的是上面这条 `FastAPI + local JSON artifacts` 主线。

仓库中还保留了 `backend/app/db/`、`backend/app/pipeline/`、`backend/app/workers/` 等下一阶段架构骨架，用于未来切换到 `SQLAlchemy + Celery`。这些模块目前未接入 `main.py`，不属于当前 MVP 运行路径。

## 本地启动

### 方式一：Docker

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000/docs`

### 方式二：本地

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## 当前实现说明

- PDF 解析主路径为：本地库只负责把页面渲染成图片，再交给 `Kimi` 提取页面文本与结构
- 音频转写优先使用 `openai-whisper`
- 如果当前环境没有装好 Whisper，音频 ingest 会写入降级提示文本，方便前端流程先跑通
- 知识点抽取当前支持两条路径：
  - 配置 `graph_llm_*` 后，优先走 OpenAI-compatible LLM 抽取 `concepts + relations`
  - 未配置 LLM 时，回退到仓库里的 `规则 + 统计` 版本
- chunk 与 concept 的 `embedding` 已预留为真实向量接口，不再推荐使用本地哈希向量
- 图结果当前仍保存在本地 `graph.json`，课堂展示版不依赖 Neo4j
- session、ingest artifact、graph artifact、note artifact 当前都保存在 `backend/artifacts/<session_id>/` 下
- 上传新文件到已有 session 时，会使旧 graph/note 失效，避免继续读取过期结果

## 模型配置

课堂展示版建议配置一条 OpenAI-compatible 接口，便于切换 `DeepSeek / Qwen / OpenAI`：

```bash
GRAPH_LLM_BASE_URL=
GRAPH_LLM_API_KEY=
GRAPH_LLM_MODEL=
```

PDF ingest 主路径默认使用 Kimi 抽页内容：

```bash
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_API_KEY=
KIMI_MODEL=kimi-k2.6
```

embedding 当前默认走本地部署的 `bge-m3`：

```bash
EMBED_PROVIDER=bge_m3
EMBEDDING_LOCAL_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_DEVICE=cpu
```

## 测试

```bash
cd backend
./.venv/bin/pytest
```
