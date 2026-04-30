from __future__ import annotations

from app.config import settings


def test_runtime_settings_do_not_expose_secret_values(client, monkeypatch, tmp_path):
    import app.api.routes.settings as settings_routes

    monkeypatch.setattr(settings_routes, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(settings, "graph_llm_api_key", "secret-value")

    response = client.get("/settings/runtime")

    assert response.status_code == 200
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert fields["GRAPH_LLM_API_KEY"]["secret"] is True
    assert fields["GRAPH_LLM_API_KEY"]["configured"] is True
    assert fields["GRAPH_LLM_API_KEY"]["value"] == ""


def test_runtime_settings_write_env_and_update_current_settings(client, monkeypatch, tmp_path):
    import app.api.routes.settings as settings_routes

    env_path = tmp_path / ".env"
    env_path.write_text("# existing\nGRAPH_LLM_MODEL=old-model\nUNCHANGED=1\n", encoding="utf-8")
    monkeypatch.setattr(settings_routes, "ENV_PATH", env_path)
    monkeypatch.setattr(settings, "graph_llm_model", "old-model")

    response = client.post(
        "/settings/runtime",
        json={"values": {"GRAPH_LLM_MODEL": "deepseek-v4-flash", "WHISPER_MODEL_SIZE": "small"}},
    )

    assert response.status_code == 200
    content = env_path.read_text(encoding="utf-8")
    assert "# existing" in content
    assert "UNCHANGED=1" in content
    assert "GRAPH_LLM_MODEL=deepseek-v4-flash" in content
    assert "WHISPER_MODEL_SIZE=small" in content
    assert settings.graph_llm_model == "deepseek-v4-flash"
    assert settings.whisper_model_size == "small"


def test_runtime_settings_reject_unknown_keys(client, monkeypatch, tmp_path):
    import app.api.routes.settings as settings_routes

    monkeypatch.setattr(settings_routes, "ENV_PATH", tmp_path / ".env")

    response = client.post("/settings/runtime", json={"values": {"DATABASE_URL": "postgres://x"}})

    assert response.status_code == 400
    assert "Unsupported setting keys" in response.text


def test_runtime_settings_empty_secret_does_not_overwrite_existing_secret(client, monkeypatch, tmp_path):
    import app.api.routes.settings as settings_routes

    env_path = tmp_path / ".env"
    env_path.write_text("GRAPH_LLM_API_KEY=old-secret\nGRAPH_LLM_MODEL=old-model\n", encoding="utf-8")
    monkeypatch.setattr(settings_routes, "ENV_PATH", env_path)
    monkeypatch.setattr(settings, "graph_llm_api_key", "old-secret")

    response = client.post(
        "/settings/runtime",
        json={"values": {"GRAPH_LLM_API_KEY": "", "GRAPH_LLM_MODEL": "new-model"}},
    )

    assert response.status_code == 200
    content = env_path.read_text(encoding="utf-8")
    assert "GRAPH_LLM_API_KEY=old-secret" in content
    assert "GRAPH_LLM_MODEL=new-model" in content
    assert settings.graph_llm_api_key == "old-secret"
