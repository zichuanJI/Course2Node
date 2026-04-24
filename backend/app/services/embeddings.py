from __future__ import annotations

from app.config import settings
from app.services.text_utils import hash_embedding


def embedding_configured() -> bool:
    if settings.embed_provider == "bge_m3":
        return bool(settings.embedding_local_model_name)
    if settings.embed_provider == "openai_compatible":
        return bool(settings.embedding_api_key and settings.embedding_model)
    if settings.embed_provider == "openai":
        return bool(settings.openai_api_key)
    return False


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    if settings.embed_provider == "bge_m3":
        provider = _local_bge_m3_provider()
    elif settings.embed_provider == "openai_compatible":
        provider = _openai_compatible_provider()
    elif settings.embed_provider == "openai":
        provider = _openai_provider()
    else:
        raise RuntimeError(f"Unsupported embed provider: {settings.embed_provider}")

    batches: list[list[float]] = []
    batch_size = max(1, settings.embedding_batch_size)
    for start in range(0, len(texts), batch_size):
        batches.extend(provider.embed(texts[start:start + batch_size]))
    return batches


def embed_query(text: str) -> list[float]:
    if embedding_configured():
        return embed_texts([text])[0]
    return hash_embedding(text)


def _local_bge_m3_provider():
    from app.providers.embed.local_bge_m3 import LocalBGEM3EmbedProvider

    return LocalBGEM3EmbedProvider(
        model_name=settings.embedding_local_model_name,
        device=settings.embedding_local_device,
        use_fp16=settings.embedding_local_use_fp16,
    )


def _openai_compatible_provider():
    from app.providers.embed.openai_compatible_embed import OpenAICompatibleEmbedProvider

    return OpenAICompatibleEmbedProvider(
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        timeout_seconds=settings.embedding_timeout_seconds,
    )


def _openai_provider():
    from app.providers.embed.openai_embed import OpenAIEmbedProvider

    return OpenAIEmbedProvider(timeout_seconds=settings.embedding_timeout_seconds)
