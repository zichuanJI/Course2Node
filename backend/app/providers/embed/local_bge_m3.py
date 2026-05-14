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
            import torch  # type: ignore
            from transformers import AutoModel, AutoTokenizer  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Local BGE-M3 embedding requires `torch` and `transformers`."
            ) from exc

        self.model_name = model_name or settings.embedding_local_model_name
        self.device = device or settings.embedding_local_device
        self.use_fp16 = settings.embedding_local_use_fp16 if use_fp16 is None else use_fp16
        self._torch = torch

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
        except Exception as exc:
            raise RuntimeError(
                "Failed to load local BGE-M3 model. "
                "This usually means the local Hugging Face cache is incomplete or the current "
                "`transformers` stack is incompatible with `BAAI/bge-m3`."
            ) from exc

        self._model.to(self.device)
        self._model.eval()
        if self.use_fp16 and str(self.device).startswith("cuda"):
            self._model.half()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        max_length = self._safe_max_length()
        batch_size = max(1, settings.embedding_batch_size)

        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}

            with self._torch.no_grad():
                outputs = self._model(**encoded)
                cls_vectors = outputs.last_hidden_state[:, 0]
                normalized = self._torch.nn.functional.normalize(cls_vectors, p=2, dim=1)

            vectors.extend(normalized.detach().cpu().tolist())

        return vectors

    def _safe_max_length(self) -> int:
        max_length = getattr(self._tokenizer, "model_max_length", 512)
        if not isinstance(max_length, int) or max_length <= 0 or max_length > 8192:
            return 8192
        return max_length
