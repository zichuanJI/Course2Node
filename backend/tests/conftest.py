from __future__ import annotations

import pytest

from app.config import settings
from app.services.text_utils import hash_embedding


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "graph_llm_base_url", "")
    monkeypatch.setattr(settings, "graph_llm_api_key", "")
    monkeypatch.setattr(settings, "graph_llm_model", "")
    monkeypatch.setattr(settings, "graph_llm_strict", True)
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "kimi_model", "kimi-k2.6")
    monkeypatch.setattr(settings, "embed_provider", "bge_m3")
    monkeypatch.setattr(settings, "embedding_local_model_name", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_local_device", "cpu")

    import app.services.embeddings as embeddings_module
    import app.services.ingestion as ingestion_module
    import app.services.graph_builder as graph_builder_module
    import app.services.search as search_module

    monkeypatch.setattr(embeddings_module, "embed_texts", lambda texts: [hash_embedding(text) for text in texts])
    monkeypatch.setattr(embeddings_module, "embed_query", lambda text: hash_embedding(text))
    monkeypatch.setattr(ingestion_module, "embed_texts", lambda texts: [hash_embedding(text) for text in texts])
    monkeypatch.setattr(graph_builder_module, "embed_texts", lambda texts: [hash_embedding(text) for text in texts])
    monkeypatch.setattr(graph_builder_module, "embedding_configured", lambda: True)
    monkeypatch.setattr(search_module, "embed_query", lambda text: hash_embedding(text))
    return tmp_path


@pytest.fixture
def client(tmp_storage):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
