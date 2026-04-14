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
  -> 知识点抽取 / 共现统计 / 规则关系抽取
  -> 构建知识点图谱
  -> 搜索知识点 / 查看子图
  -> 生成结构化笔记
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/upload/pdf` | 上传 PDF |
| POST | `/upload/audio` | 上传音频 |
| POST | `/ingest/pdf` | 解析 PDF，生成证据块 |
| POST | `/ingest/audio` | 转写音频，生成证据块 |
| POST | `/build_graph` | 构建知识点主图 |
| POST | `/search` | 搜索知识点与证据片段 |
| GET | `/graph/subgraph` | 查看某个知识点的局部关系图 |
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
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## 当前实现说明

- PDF 解析使用 `PyMuPDF`
- 音频转写优先使用 `openai-whisper`
- 如果当前环境没有装好 Whisper，音频 ingest 会写入降级提示文本，方便前端流程先跑通
- 知识点抽取、关系抽取、聚类和笔记生成目前是 `规则 + 统计` 版本，接口已经稳定，后续可替换为 LLM / Neo4j 实现
