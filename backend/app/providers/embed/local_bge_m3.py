"""Local BGE-M3 embedding adapter."""
from __future__ import annotations

from app.config import settings
from app.core.providers import EmbedProvider


class LocalBGEM3EmbedProvider(EmbedProvider):
    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        use_fp16: bool | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Local BGE-M3 embedding requires the `sentence-transformers` package."
            ) from exc

        self.model_name = model_name or settings.embedding_local_model_name
        self.device = device or settings.embedding_local_device
        self.use_fp16 = settings.embedding_local_use_fp16 if use_fp16 is None else use_fp16
        model_kwargs = {"device": self.device}
        if self.use_fp16:
            model_kwargs["model_kwargs"] = {"torch_dtype": "auto"}
        self._model = SentenceTransformer(self.model_name, **model_kwargs)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = self._model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in result]
