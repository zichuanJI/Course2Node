from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://course2note:course2note@localhost:5432/course2note"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Storage
    storage_backend: str = "local"
    local_storage_path: str = "/artifacts"

    # LLM
    synthesize_llm_provider: str = "claude"  # claude | gemini
    retrieve_llm_provider: str = "minimax"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    minimax_api_key: str = ""
    minimax_group_id: str = ""

    # Embed
    embed_provider: str = "openai"  # openai | gemini
    openai_api_key: str = ""

    # Search
    search_provider: str = "tavily"  # tavily | bing
    tavily_api_key: str = ""
    bing_search_api_key: str = ""


settings = Settings()
