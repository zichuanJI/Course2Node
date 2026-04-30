# Course2Node 项目汇报与维护说明

## 项目总览

Course2Node 面向数据科学课程展示：用户上传课堂 PDF、音频或二者组合，系统将原始材料转为文本 chunk，生成语义向量，再抽取知识点与关系构建课程图谱。图谱下游目前支持结构化笔记生成和基于重要度的出卷。

当前主流程：

1. `upload`：上传 PDF/音频，创建或追加课程 session。
2. `ingest`：PDF 通过 Kimi 抽取文本，音频通过 Whisper/faster-whisper 转写。
3. `chunk + embedding`：文本切分为 chunk，并通过当前默认 BGE-M3 生成语义向量。
4. `build_graph`：LLM 或规则抽取概念与关系，计算图指标和 topic cluster。
5. `workspace`：前端展示概念图、检索、节点详情、笔记和试卷。

## 文件树与重要文件职责

```text
Course2Note/
├── README.md                         # 启动、配置、部署说明
├── course2node.md                    # 本文件：汇报与维护参考
├── docker-compose.yml                # 容器化启动配置
├── backend/
│   ├── app/config.py                 # 环境变量与默认配置
│   ├── app/main.py                   # FastAPI 入口与路由挂载
│   ├── app/core/types.py             # Pydantic 数据结构
│   ├── app/api/routes/upload.py      # 文件上传与旧产物失效
│   ├── app/api/routes/graph.py       # ingest、构图、搜索、笔记、出卷 API
│   ├── app/api/routes/export.py      # 笔记/试卷导出
│   ├── app/api/routes/settings.py    # 首页部署设置 API，写入本地 .env
│   ├── app/storage/local.py          # session、ingest、graph、notes、exam 本地 JSON 存储
│   ├── app/services/ingestion.py     # PDF/音频 ingest，chunk 与 embedding 写入
│   ├── app/services/kimi_pdf.py      # Kimi 文件解析与 PDF 文本抽取
│   ├── app/services/embeddings.py    # embedding provider 分发
│   ├── app/providers/embed/local_bge_m3.py # 本地 BGE-M3 embedding 适配
│   ├── app/services/llm_graph.py     # 图谱抽取 prompt 与 LLM JSON 清洗
│   ├── app/services/graph_builder.py # 概念/边构建、图指标、聚类
│   ├── app/services/search.py        # 概念与 chunk 检索、子图提取
│   ├── app/services/notes.py         # 图谱驱动笔记 prompt 与生成
│   ├── app/services/exam.py          # 图谱驱动出卷 prompt 与生成
│   └── tests/                        # 后端服务/API 测试
└── frontend/
    ├── src/pages/HomePage.tsx        # 首页课程列表、删除、部署设置入口
    ├── src/pages/NewSessionPage.tsx  # 新建课程与文件上传
    ├── src/pages/PipelinePage.tsx    # 上传后 ingest/build_graph 流程
    ├── src/pages/WorkspacePage.tsx   # 图谱、检索、笔记、出卷工作区
    ├── src/api/client.ts             # 前端 API client
    ├── src/types/index.ts            # 前端数据类型
    ├── src/components/graph/ConceptGraph.tsx # ReactFlow 图谱渲染
    ├── src/components/graph/layoutUtils.ts   # force/radial/cluster 布局算法
    ├── src/components/graph/ConceptDrawer.tsx # 节点详情卡片
    ├── src/components/search/SearchPanel.tsx # 左侧知识点/内容检索
    └── src/components/notes/          # 笔记、试卷、Markdown、导出菜单
```

## 数据科学相关知识点

### 当前实际使用

- **Kimi PDF 文本抽取**：Kimi 只用于 PDF 文件内容抽取，不用于 embedding。相关入口在 `kimi_pdf.py` 和 `ingestion.py`。
- **Whisper ASR**：音频转写依次尝试 `openai-whisper`、本地 `faster-whisper` 和外部 faster-whisper runner。音频先经 `ffmpeg` 转为 16kHz 单声道 WAV。
- **文本清洗与 chunking**：`text_utils.py` 对换行、空白、句子边界做规范化，`split_text` 按长度和 overlap 切分 chunk。
- **候选词抽取**：英文用正则 token，中文优先使用 Jieba 词性筛选名词、专名、动名词等候选术语。
- **BGE-M3 语义 embedding**：当前 `.env` 与默认配置使用 `EMBED_PROVIDER=bge_m3`，通过 `sentence-transformers` 加载 `BAAI/bge-m3`，对 chunk、concept 和 query 生成归一化语义向量。
- **cosine similarity**：检索时用 query 向量与 concept/chunk 向量做余弦相似度计算，并叠加 lexical bonus。
- **LLM 图谱抽取**：`llm_graph.py` 用 prompt 要求模型输出概念、别名、定义、关键点、标签、前置概念、应用和关系边 JSON。
- **图数据库建模**：`ConceptNode` 表示知识点节点，`GraphEdge` 表示 `RELATES_TO`、`CO_OCCURS_WITH` 等关系边。
- **共现关系**：规则 fallback 中，同一 chunk 内共同出现的概念会形成共现计数和 `CO_OCCURS_WITH` 边。
- **图中心性指标**：`graph_builder.py` 计算 degree centrality、weighted degree centrality、betweenness centrality、closeness centrality。
- **重要度公式**：当前 `importance_score = 0.45 * weighted_degree + 0.25 * betweenness + 0.20 * closeness + 0.10 * degree`。
- **连通分量聚类**：topic cluster 基于无向关系图的 connected components，再按重要度排序形成主题簇。
- **图布局算法**：前端 `layoutUtils.ts` 包含 Fruchterman-Reingold 力导向布局、按度中心节点的 radial layout、按 topic cluster 分组的 cluster layout。
- **图谱驱动生成**：笔记和出卷 prompt 会把图指标、聚类、概念摘要和关系边传给 LLM，高重要度和高中介中心度概念获得更高权重。

### 可选支持但不一定当前启用

- `EMBED_PROVIDER=openai`：可用 OpenAI embedding。
- `EMBED_PROVIDER=openai_compatible`：可接 DeepSeek/Qwen/DashScope 等兼容服务，但需要配置 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`。
- `hash_embedding`：测试和兜底检索中可用的本地启发式哈希向量，不是当前生产 embedding 方案。

## 关键调试入口

- PDF 抽取失败：检查 `KIMI_API_KEY`、`KIMI_MODEL`、`KIMI_TIMEOUT_SECONDS`，入口在 `kimi_pdf.py`。
- 音频失败：检查 `ffmpeg`、`WHISPER_MODEL_SIZE`、`FASTER_WHISPER_PYTHON_PATH`，入口在 `ingestion.py`。
- 图谱质量差：优先调 `llm_graph.py` 的图谱抽取 prompt，再看 `graph_builder.py` 的清洗、边构建和图指标。
- 笔记质量差：调 `notes.py` 中 `NOTE_STYLE_RULES` 和 prompt 构造。
- 出卷质量差：调 `exam.py` 中 `EXAM_SYSTEM_PROMPT` 和 `EXAM_STYLE_RULES`。
- 图布局异常：调 `ConceptGraph.tsx` 和 `layoutUtils.ts`，确认 node 尺寸、handle 位置和 layout 坐标是否一致。
- 部署换 key：首页“部署设置”窗口会调用 `settings.py` 写入后端 `.env`。
