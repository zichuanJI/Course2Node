# Course2Node 🧠✨

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 20+](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)
[![ReactFlow](https://img.shields.io/badge/UI-ReactFlow-ff007f.svg)](https://reactflow.dev/)

**Course2Node** 是一款智能化、可视化的课程知识图谱构建工具。它能够将零散的课程资源（PDF 课件、讲义笔记、课堂实录音频）自动化地转化为结构化的知识图谱，辅助学生和教研人员进行沉浸式的复习与知识点关联探索。

本项目诞生于**南京大学信息管理学院 数据科学与数据分析课程**的小组项目。如果你觉得这个项目对你有所启发，请给我们一个 **Star ⭐️**！

---

## 🎯 项目目的 (Why Course2Node?)

传统的课程学习往往伴随着海量、线性的课件和录音，难以在脑海中建立立体的知识网络。Course2Node 旨在：
1. **打破信息孤岛**：将一门课中数十个 PDF 和语音实录统一处理，自动提取核心概念。
2. **可视化知识关联**：利用 LLM 提取概念间的上下文联系，并以力导向图的形式直观呈现，支持跨章节的语义联想。
3. **结构化沉淀**：基于图谱自动生成高质量的 Markdown 笔记，辅助复习。
4. **智能自测反馈**：根据图谱中的重要节点和关系，动态生成练习题进行知识点检测。

---

## ✨ 核心特性 (Features)

- **📚 多模态数据摄入 (Ingestion)**：
  - 支持 **PDF** 文档的高效抽取与版面解析（通过 Kimi API）。
  - 支持 **音频文件** 的语音识别与高精度转写（集成 Whisper / faster-whisper）。
- **🧠 智能知识抽取 (Knowledge Extraction)**：
  - 支持调用兼容 OpenAI 格式的大语言模型，自动化抽取概念 (Concepts)、属性和语义关系 (Relations)。
  - 内置基于重要度和向量相似度的**跨章节知识融合**，智能连接不同讲次间的相关考点。
- **🕸 交互式图谱可视化 (Graph Visualization)**：
  - 基于 ReactFlow 的前端交互体验，支持力导向 (Force)、径向 (Radial)、聚类 (Cluster) 三种高级图谱布局。
  - 支持点击节点展开详情侧边栏、全局高亮关联节点、无缝缩放和拖拽。
- **🔍 语义级全站检索 (Semantic Search)**：
  - 内置本地 `BAAI/bge-m3` 向量检索模型（也支持接入云端 Embedding 服务）。
  - 支持混合检索，随时定位关键知识点对应的原始文本块 (Chunks)。
- **📝 一键生成笔记与导出 (Notes & Export)**：
  - 根据提取出的图谱一键生成结构化的知识笔记，支持 Markdown、TeX、纯文本导出。

---

## 🏗️ 架构与目录结构 (Architecture & Structure)

项目采用前后端分离的现代 Web 架构，核心产物 (Artifacts) 均以本地 JSON 形式落盘，实现轻量级持久化。

```text
Course2Node/
├── backend/                  # 🐍 核心算法层与后端服务 (Python + FastAPI)
│   ├── app/
│   │   ├── api/routes/       # FastAPI 路由控制器 (上传, 图谱, 检索, 导出)
│   │   ├── core/types.py     # 核心实体类定义 (基于 Pydantic)
│   │   ├── providers/        # LLM, Embedding, 外部 API 的适配层
│   │   ├── services/         # 核心业务逻辑实现
│   │   │   ├── ingestion.py  # 音视频与文档切块引擎
│   │   │   ├── kimi_pdf.py   # Kimi 文本智能提取
│   │   │   ├── llm_graph.py  # 图谱与关系提取 Prompt 引擎
│   │   │   ├── graph_builder.py # 中心度计算、社区发现与总图谱融合
│   │   │   └── notes.py / exam.py # 生成式学习辅助工具
│   │   └── storage/          # 本地 Artifacts IO 读写管理
│   └── tests/                # 自动化测试用例
├── frontend/                 # ⚛️ 交互层 (Vite + React + TypeScript)
│   └── src/
│       ├── api/              # API Client (与后端通信)
│       ├── components/       # UI 组件库 (Graph, Notes, Search, Primitives)
│       ├── pages/            # 路由页面 (Workspace, Pipeline, Home)
│       └── styles/           # CSS Tokens 设计规范
├── artifacts/                # 📂 运行时产生的知识数据 (图谱, 笔记, chunks)
└── docker-compose.yml        # 🐳 一键部署配置 (可选)
```

---

## 🚀 快速开始 (Getting Started)

### 0. 环境要求
- **Python** 3.11 或 3.12
- **Node.js** 20+ 或 22+
- **ffmpeg** (用于音频处理及 Whisper 转写)
- **大模型 API Key** (需自备 Kimi API 及兼容 OpenAI 格式的 LLM API)

#### 安装 FFmpeg
* **macOS**: `brew install ffmpeg`
* **Windows**: 使用管理员身份打开 PowerShell 执行 `winget install Gyan.FFmpeg`
*(安装后请重启终端并运行 `ffmpeg -version` 确认生效)*

### 1. 配置环境变量

从示例文件复制环境变量配置，并填入你自己的 API Key：

**macOS / Linux**
```bash
cp .env.example .env
```

**Windows PowerShell**
```powershell
Copy-Item .env.example .env
```

**推荐的 `.env` 核心配置：**
```ini
# --- 存储 ---
LOCAL_STORAGE_PATH=./artifacts

# --- 图谱抽取大模型 (需填入真实有效的 Key) ---
GRAPH_LLM_BASE_URL=https://api.deepseek.com/v1
GRAPH_LLM_API_KEY=sk-your-llm-key
GRAPH_LLM_MODEL=deepseek-chat

# --- PDF文档提取模型 (Kimi) ---
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_API_KEY=sk-your-kimi-key
KIMI_MODEL=kimi-k2.6

# --- 向量模型引擎 ---
EMBED_PROVIDER=bge_m3
EMBEDDING_LOCAL_MODEL_NAME=BAAI/bge-m3

# --- 语音识别配置 ---
WHISPER_MODEL_SIZE=base
WHISPER_LANGUAGE=auto
```

### 2. 启动后端 (Backend)

后端基于 FastAPI 提供数据服务。

**🍎 macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel -i https://mirrors.aliyun.com/pypi/simple/
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**🪟 Windows PowerShell**
*(注意：为解决 Windows 环境下 `openai-whisper` 构建问题，推荐使用如下包含 `--no-build-isolation` 的安装策略)*
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip wheel packaging "setuptools==69.5.1" -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --no-build-isolation -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. 启动前端 (Frontend)

请新开一个终端窗口进行操作。

**🍎 macOS / Linux**
```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

**🪟 Windows PowerShell**
```powershell
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173
```

🎉 **全部就绪！**
浏览器打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)** 即可开始构建你的知识图谱。
*(后端 API 接口文档可访问: http://127.0.0.1:8000/docs)*

---

## 🐳 使用 Docker 一键部署

对于希望保持环境整洁的用户，或进行线上部署演示，可以直接使用 Docker Compose。

*(请确保 `.env` 中 `LOCAL_STORAGE_PATH` 被设为了 `/artifacts`)*

```bash
docker compose up --build
```
启动后同样访问 `http://127.0.0.1:5173` 即可。

---

## 🛠️ 常见问题 (FAQ & Troubleshooting)

| 问题描述 | 解决方案 |
| :--- | :--- |
| **首次运行极慢 / 进度条卡住不动** | 本地首次运行 `BAAI/bge-m3` 和 `Whisper` 模型时，后台会从 HuggingFace 下载数十 GB 的权重文件。请保持网络通畅耐心等待。 |
| **`Kimi PDF extraction is not configured`** | 说明 `.env` 中的 `KIMI_API_KEY` 未配置或读取失败。请检查根目录下是否存在合法的 `.env`。 |
| **`LLM graph extraction returned no valid concepts`** | 大模型抽取图谱超时或理解异常。请确保 `GRAPH_LLM_API_KEY` 配置正确且账户有余额。遇到极其长篇的内容可以适当调大 `GRAPH_LLM_TIMEOUT_SECONDS`。 |
| **音频转写失败 (ASR failed)** | 请首先排查机器是否成功安装了 `ffmpeg` 并加入环境变量。如果是 Windows，还需要确认命令行是否能全局调用 `ffmpeg`。 |
| **重启后端后之前的课程找不到了** | 请检查 `.env` 中的 `LOCAL_STORAGE_PATH` 是否使用的是**绝对路径**。如果是相对路径且启动路径发生了改变，可能导致找不到先前的 Artifacts 存档。 |

---

## 🤝 参与贡献 (Contributing)

我们非常欢迎对该项目的各种改进：
1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 发起一个 Pull Request

代码风格与检查命令参考：
```bash
# 后端测试
cd backend && .venv/bin/python -m pytest
# 前端生产构建测试
cd frontend && npm run build
```

---

## 📄 许可证 (License)

本项目基于 [MIT License](https://opensource.org/licenses/MIT) 开源。请自由地将其用于学习、研究与个人创造。

*Built with ❤️ for better learning experiences.*
