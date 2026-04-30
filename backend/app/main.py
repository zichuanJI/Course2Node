from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import export, graph, sessions, settings as runtime_settings, upload
from app.config import settings

app = FastAPI(title="Course2Node API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(graph.router)
app.include_router(export.router)
app.include_router(runtime_settings.router)


@app.get("/health")
async def health():
    return {"status": "ok", "storage_path": settings.local_storage_path}
