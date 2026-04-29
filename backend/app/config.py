from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://course2note:course2note@localhost:5432/course2note"

    # Storage
    storage_backend: str = "local"
    local_storage_path: str = str(ROOT_DIR / "artifacts")

    # LLM
    synthesize_llm_provider: str = "claude"  # claude | gemini
    retrieve_llm_provider: str = "minimax"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    minimax_api_key: str = ""
    minimax_group_id: str = ""
    graph_llm_base_url: str = ""
    graph_llm_api_key: str = ""
    graph_llm_model: str = ""
    graph_llm_timeout_seconds: float = 60.0
    graph_llm_batch_max_chars: int = 5200
    graph_llm_batch_max_chunks: int = 8
    graph_llm_max_input_units: int = 0
    graph_llm_max_output_tokens: int = 6000
    graph_llm_strict: bool = True
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_api_key: str = ""
    kimi_model: str = "kimi-k2.6"
    kimi_timeout_seconds: float = 60.0
    kimi_max_output_tokens: int = 2200

    # Embed
    embed_provider: str = "bge_m3"  # bge_m3 | openai | openai_compatible
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_timeout_seconds: float = 30.0
    embedding_batch_size: int = 32
    embedding_local_model_name: str = "BAAI/bge-m3"
    embedding_local_device: str = "cpu"
    embedding_local_use_fp16: bool = False
    openai_api_key: str = ""
    embedding_dimensions: int = 1024
    whisper_model_size: str = "base"
    whisper_language: str = "auto"
    faster_whisper_python_path: str = "/Users/zicheng/Documents/Playground/2026.3.13 Video-Note-Tool/.venv/bin/python"
    faster_whisper_runner_path: str = str(Path(__file__).resolve().parent / "services" / "faster_whisper_runner.py")

    # Search
    search_provider: str = "tavily"  # tavily | bing
    tavily_api_key: str = ""
    bing_search_api_key: str = ""


settings = Settings()
