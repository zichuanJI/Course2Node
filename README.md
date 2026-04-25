# Course2Node

Course2Node turns lecture PDFs, slides, notes, and audio into a knowledge-point graph for classroom demos. The current MVP focuses on the full backend flow: upload files, extract text chunks, generate semantic embeddings, ask an LLM to extract concepts and relations, then return a graph that the frontend can render and inspect.

## What Works Now

- PDF ingest: PDF pages are rendered and sent to Kimi for page-aware text extraction.
- Audio ingest: lecture audio is transcribed with local Whisper or faster-whisper.
- Embedding: chunks use a real embedding provider. The default is local `BAAI/bge-m3`.
- Graph extraction: an OpenAI-compatible chat model extracts concepts, node attributes, evidence references, and relations.
- Storage: sessions, uploads, chunks, graphs, and notes are stored as local JSON artifacts.
- Frontend: Vite/React UI connects to the FastAPI backend and visualizes the generated graph.

## Repository Layout

```text
backend/
  app/
    api/routes/        FastAPI route handlers
    services/          ingestion, embedding, graph extraction, search, notes
    providers/         LLM, embedding, and search provider adapters
    storage/local.py   local artifact persistence
  tests/               backend service tests
frontend/
  src/                 React app, graph UI, search panel, API client
artifacts/             local runtime data, ignored by git
docker-compose.yml     optional two-service local stack
```

## Required Runtime

- Python 3.11 or 3.12
- Node.js 20+ or 22+
- `ffmpeg` for audio conversion and Whisper transcription
- Network access on first model use, because `bge-m3` and Whisper models may download weights
- API keys for Kimi and the graph LLM

On macOS, install `ffmpeg` with:

```bash
brew install ffmpeg
```

## Configuration

Copy the sample env file at the repository root:

```bash
cp .env.example .env
```

Never commit `.env` or real API keys. The backend loads `.env` from the repository root.

### Core Settings

| Variable | Required | Purpose |
| --- | --- | --- |
| `LOCAL_STORAGE_PATH` | Yes | Where uploaded files and generated JSON artifacts are stored. Prefer an absolute path for local development. Use `/artifacts` when running Docker. |
| `GRAPH_LLM_BASE_URL` | Yes | OpenAI-compatible chat API base URL, for example `https://api.deepseek.com/v1`. |
| `GRAPH_LLM_API_KEY` | Yes | API key for the graph extraction model. |
| `GRAPH_LLM_MODEL` | Yes | Chat model name used to extract concepts and relations. |
| `KIMI_BASE_URL` | Yes | Kimi OpenAI-compatible base URL. Keep `https://api.moonshot.cn/v1` unless the provider changes. |
| `KIMI_API_KEY` | Yes for PDF | Kimi API key for PDF text extraction. |
| `KIMI_MODEL` | Yes for PDF | Kimi model name. Current target is `kimi-k2.6`. |
| `EMBED_PROVIDER` | Yes | `bge_m3`, `openai`, or `openai_compatible`. Default is local `bge_m3`. |
| `EMBEDDING_LOCAL_MODEL_NAME` | Yes for bge-m3 | Default `BAAI/bge-m3`. First run downloads the model. |
| `WHISPER_MODEL_SIZE` | Yes for audio | Whisper model size, for example `base`, `small`, or `medium`. |
| `WHISPER_LANGUAGE` | Optional | `auto` by default. Set `zh` or `en` if auto-detection is unstable. |
| `VITE_API_BASE_URL` | Optional | Frontend API base URL. Defaults to `http://localhost:8000`. For local Vite runs, put it in `frontend/.env.local`; Docker injects it from `docker-compose.yml`. |

Recommended local `.env` shape:

```bash
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/absolute/path/to/Course2Note/artifacts

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

If you use an OpenAI-compatible embedding API instead of local bge-m3:

```bash
EMBED_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-provider/v1
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_MODEL=your-embedding-model
```

## Local Development

Start the backend:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

If the backend is not on `http://localhost:8000`, create `frontend/.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Open:

- Frontend: `http://127.0.0.1:5173`
- Backend docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Docker Development

Docker is useful for a clean demo environment. Before starting, set this in `.env`:

```bash
LOCAL_STORAGE_PATH=/artifacts
```

Then run:

```bash
docker compose up --build
```

Docker exposes the same ports: frontend on `5173`, backend on `8000`.

## Processing Flow

1. Upload one or more PDFs and/or audio files.
2. Run ingest. PDFs go through Kimi page extraction. Audio goes through Whisper transcription.
3. Each text chunk receives an embedding.
4. `build_graph` sends chunks to the configured graph LLM.
5. The backend cleans concepts, validates evidence references, builds relations, and writes `graph.json`.
6. The frontend loads the graph, search index, evidence cards, and node detail panel from backend artifacts.

Runtime artifacts are written under `LOCAL_STORAGE_PATH/<session_id>/`.

## Testing

Backend tests:

```bash
cd backend
.venv/bin/python -m pytest
```

Backend syntax check:

```bash
cd backend
.venv/bin/python -m compileall app tests
```

Frontend production build:

```bash
cd frontend
npm run build
```

## Troubleshooting

- `Kimi PDF extraction is not configured`: set `KIMI_API_KEY` and `KIMI_MODEL`.
- `LLM graph extraction returned no valid concepts`: check `GRAPH_LLM_*`, inspect whether ingest produced meaningful chunks, and increase `GRAPH_LLM_TIMEOUT_SECONDS` if needed.
- `ASR failed`: install `ffmpeg`, ensure `faster-whisper` or `openai-whisper` is installed in the backend venv, and try a smaller `WHISPER_MODEL_SIZE`.
- First run is slow: local bge-m3 and Whisper may download model weights and initialize on CPU.
- Old courses disappear between restarts: use a stable absolute `LOCAL_STORAGE_PATH`.

## Notes

The current MVP uses local JSON artifacts instead of Neo4j. Neo4j or SQL-backed persistence can be added later, but the classroom demo path does not require it.
