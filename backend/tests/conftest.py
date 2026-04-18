from __future__ import annotations

import pytest

from app.config import settings


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "graph_llm_base_url", "")
    monkeypatch.setattr(settings, "graph_llm_api_key", "")
    monkeypatch.setattr(settings, "graph_llm_model", "")
    monkeypatch.setattr(settings, "graph_llm_strict", True)
    monkeypatch.setattr(settings, "pdf_vision_base_url", "")
    monkeypatch.setattr(settings, "pdf_vision_api_key", "")
    monkeypatch.setattr(settings, "pdf_vision_model", "")
    return tmp_path


@pytest.fixture
def client(tmp_storage):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
