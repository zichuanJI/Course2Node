from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import export, graph, sessions, upload
from app.config import settings

app = FastAPI(title="Course2Node API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(graph.router)
app.include_router(export.router)


@app.get("/health")
async def health():
    return {"status": "ok", "storage_path": settings.local_storage_path}
