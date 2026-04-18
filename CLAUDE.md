# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
./.venv/bin/uvicorn app.main:app --reload        # dev server (port 8000)
./.venv/bin/pytest                               # all tests
./.venv/bin/pytest tests/test_api_flow.py -k test_name  # single test
```

### Frontend
```bash
cd frontend
npm run dev      # dev server (port 5173, may fall back to 5174+)
npm run build    # tsc + vite build (verifies zero TS errors)
npm run preview  # preview production build
```

### Full stack (Docker)
```bash
cp .env.example .env   # then fill in LLM keys
docker compose up --build
```

## Environment variables (`.env` in repo root)

The backend reads these at startup via `app/config.py` (pydantic-settings):

```
# LLM for graph extraction (OpenAI-compatible; any DeepSeek/Qwen/OpenAI endpoint)
GRAPH_LLM_BASE_URL=
GRAPH_LLM_API_KEY=
GRAPH_LLM_MODEL=

# Optional: vision fallback for image-heavy PDFs
PDF_VISION_BASE_URL=
PDF_VISION_API_KEY=
PDF_VISION_MODEL=
```

Without `GRAPH_LLM_*`, graph extraction falls back to the rule+statistics path in `app/services/text_utils.py`.

## Architecture overview

### Data flow

```
upload PDF/audio  →  /ingest/pdf or /ingest/audio  →  IngestArtifact (chunks)
                  →  /build_graph  →  GraphArtifact (concepts + edges + clusters)
                  →  /generate_notes  →  NoteDocument
                  →  /export/{session_id}/{fmt}  →  markdown / tex / txt
```

All artifacts persist as JSON under `artifacts/<session_id>/` (no database required for the current MVP).

### Backend (`backend/app/`)

| Path | Role |
|---|---|
| `core/types.py` | **Single source of truth for all Pydantic models**: `CourseSession`, `GraphArtifact`, `ConceptNode`, `GraphEdge`, `IngestArtifact`, `NoteDocument`, etc. Read this before touching any data structure. |
| `storage/local.py` | JSON-file persistence layer. All load/save helpers are here; nothing else should read from the filesystem directly. |
| `api/routes/` | FastAPI routers: `upload`, `sessions`, `graph`, `export`. Routes are thin — they call service functions and return the result. |
| `services/ingestion.py` | PDF parsing (PyMuPDF) and audio transcription (Whisper via subprocess runner). |
| `services/graph_builder.py` | Orchestrates concept/relation extraction. Calls `llm_graph.py` if configured, otherwise falls back to `text_utils.py` rule extraction. |
| `services/llm_graph.py` | OpenAI-compatible LLM batched extraction. System prompt is in this file. |
| `services/notes.py` | Structured note generation from a `GraphArtifact`. |
| `services/search.py` | Keyword + embedding search over `IngestArtifact` chunks. |
| `providers/llm/openai_compatible.py` | Thin HTTP client wrapping the OpenAI chat completions API. Used by `llm_graph.py`. |

**Inactive next-phase code** (not wired into `main.py`): `app/db/`, `app/pipeline/`, `app/workers/`. Do not modify these without explicit instructions.

### Frontend (`frontend/src/`)

React 18 + TypeScript, Vite, react-router-dom v6. The workspace page is lazy-loaded to keep the initial bundle small.

**Routing**
```
/                       HomePage          — session list
/new                    NewSessionPage    — 3-step upload wizard
/session/:id/pipeline   PipelinePage      — ingest progress + SVG animation
/session/:id            WorkspacePage     — search | graph | notes (3-pane)
```

**State that lives in `App.tsx`** (persisted to `localStorage`):
- `c2n:theme` — one of `copper | ink | forest | violet`; applied as `data-theme` on `<html>`
- `c2n:graphStyle` — one of `force | radial | cluster`; passed as prop to `WorkspacePage`

**Key component roles**
| Component | Role |
|---|---|
| `components/layout/TopBar` | Brand mark, nav links, ⌘K trigger, tweaks toggle |
| `components/layout/CommandPalette` | Global ⌘K search; fetches session list from API |
| `components/layout/TweaksPanel` | Fixed bottom-right; sets `data-theme` + `graphStyle` |
| `components/graph/ConceptGraph` | reactflow + dagre layout; 3 layout modes |
| `components/graph/ConceptDrawer` | Card-stack drawer (hero → definition → stats → evidence → neighbors) |
| `components/notes/Markdown` | react-markdown + remark-gfm + remark-math + rehype-katex renderer |
| `api/client.ts` | All fetch calls; `uploadPdfWithProgress` / `uploadAudioWithProgress` use XHR (not fetch) for upload progress events |
| `hooks/useSessionStatus.ts` | Polling hook (1500 ms, degrades to 3000 ms after 30 s) used by PipelinePage |

### CSS design system

All design tokens are CSS custom properties in `src/styles/theme.css`. New components use the short-name set:

```
--bg / --panel / --panel-2    backgrounds
--ink / --ink-2 / --ink-3 / --ink-4    text hierarchy
--accent / --accent-2 / --accent-soft / --accent-ghost    brand color
--rule / --rule-strong    borders
--ok / --warn / --err / --info    semantic colors
--font-serif / --font-ui / --font-mono    typefaces
--shadow-1 / --shadow-2 / --shadow-3    elevation
```

Legacy tokens (`--bg-color`, `--accent-color`, etc.) are kept for backward compat in older component CSS files. Don't use them in new code.

Theme presets (`data-theme="copper|ink|forest|violet"`) override the accent and background tokens. The default is `copper`.

`color-mix(in oklab, ...)` is used in `ConceptDrawer` hero cards — requires Safari ≥ 16.2 / Chrome ≥ 111.

### CORS

Backend CORS is set to `allow_origins=["*"]` for development (`app/main.py`). Tighten before any production deploy.
