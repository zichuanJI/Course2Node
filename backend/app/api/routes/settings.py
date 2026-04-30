from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import ROOT_DIR, settings
from app.core.types import RuntimeSettingField, RuntimeSettingsResponse, RuntimeSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_PATH = ROOT_DIR / ".env"

DEEPSEEK_DOCS = "https://api-docs.deepseek.com/"
KIMI_PLATFORM = "https://platform.moonshot.ai/"
OPENAI_KEY_HELP = "https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key"
DASHSCOPE_KEY_HELP = "https://www.alibabacloud.com/help/doc-detail/2712195.html"
WHISPER_MODEL = "https://huggingface.co/openai/whisper-base"
FASTER_WHISPER_MODELS = "https://huggingface.co/collections/Systran/faster-whisper"

SETTING_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "GRAPH_LLM_BASE_URL",
        "attr": "graph_llm_base_url",
        "label": "图谱/笔记 LLM Base URL",
        "group": "图谱/笔记 LLM",
        "placeholder": "https://api.deepseek.com/v1",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "GRAPH_LLM_API_KEY",
        "attr": "graph_llm_api_key",
        "label": "图谱/笔记 LLM API Key",
        "group": "图谱/笔记 LLM",
        "secret": True,
        "placeholder": "sk-...",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "GRAPH_LLM_MODEL",
        "attr": "graph_llm_model",
        "label": "图谱/笔记 LLM 模型",
        "group": "图谱/笔记 LLM",
        "placeholder": "deepseek-v4-flash",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "EXAM_LLM_BASE_URL",
        "attr": "exam_llm_base_url",
        "label": "出卷 LLM Base URL",
        "group": "出卷 LLM",
        "placeholder": "https://api.deepseek.com",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "EXAM_LLM_API_KEY",
        "attr": "exam_llm_api_key",
        "label": "出卷 LLM API Key",
        "group": "出卷 LLM",
        "secret": True,
        "placeholder": "sk-...",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "EXAM_LLM_MODEL",
        "attr": "exam_llm_model",
        "label": "出卷 LLM 模型",
        "group": "出卷 LLM",
        "placeholder": "deepseek-v4-pro",
        "help_url": DEEPSEEK_DOCS,
    },
    {
        "key": "KIMI_BASE_URL",
        "attr": "kimi_base_url",
        "label": "Kimi Base URL",
        "group": "Kimi PDF",
        "placeholder": "https://api.moonshot.cn/v1",
        "help_url": KIMI_PLATFORM,
    },
    {
        "key": "KIMI_API_KEY",
        "attr": "kimi_api_key",
        "label": "Kimi API Key",
        "group": "Kimi PDF",
        "secret": True,
        "placeholder": "sk-...",
        "help_url": KIMI_PLATFORM,
    },
    {
        "key": "KIMI_MODEL",
        "attr": "kimi_model",
        "label": "Kimi 模型",
        "group": "Kimi PDF",
        "placeholder": "kimi-k2.6",
        "help_url": KIMI_PLATFORM,
    },
    {
        "key": "EMBED_PROVIDER",
        "attr": "embed_provider",
        "label": "Embedding Provider",
        "group": "Embedding",
        "placeholder": "bge_m3",
        "help_url": "https://huggingface.co/BAAI/bge-m3",
    },
    {
        "key": "EMBEDDING_LOCAL_MODEL_NAME",
        "attr": "embedding_local_model_name",
        "label": "本地 Embedding 模型",
        "group": "Embedding",
        "placeholder": "BAAI/bge-m3",
        "help_url": "https://huggingface.co/BAAI/bge-m3",
    },
    {
        "key": "EMBEDDING_BASE_URL",
        "attr": "embedding_base_url",
        "label": "OpenAI-compatible Embedding Base URL",
        "group": "Embedding",
        "placeholder": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "help_url": DASHSCOPE_KEY_HELP,
    },
    {
        "key": "EMBEDDING_API_KEY",
        "attr": "embedding_api_key",
        "label": "Embedding API Key",
        "group": "Embedding",
        "secret": True,
        "placeholder": "sk-...",
        "help_url": DASHSCOPE_KEY_HELP,
    },
    {
        "key": "EMBEDDING_MODEL",
        "attr": "embedding_model",
        "label": "Embedding 模型名",
        "group": "Embedding",
        "placeholder": "text-embedding-v4",
        "help_url": DASHSCOPE_KEY_HELP,
    },
    {
        "key": "OPENAI_API_KEY",
        "attr": "openai_api_key",
        "label": "OpenAI API Key",
        "group": "Embedding",
        "secret": True,
        "placeholder": "sk-...",
        "help_url": OPENAI_KEY_HELP,
    },
    {
        "key": "WHISPER_MODEL_SIZE",
        "attr": "whisper_model_size",
        "label": "Whisper 模型大小",
        "group": "音频 ASR",
        "placeholder": "base",
        "help_url": WHISPER_MODEL,
    },
    {
        "key": "WHISPER_LANGUAGE",
        "attr": "whisper_language",
        "label": "Whisper 语言",
        "group": "音频 ASR",
        "placeholder": "auto",
        "help_url": WHISPER_MODEL,
    },
    {
        "key": "FASTER_WHISPER_PYTHON_PATH",
        "attr": "faster_whisper_python_path",
        "label": "外部 faster-whisper Python",
        "group": "音频 ASR",
        "placeholder": "/path/to/.venv/bin/python",
        "help_url": FASTER_WHISPER_MODELS,
    },
]

SETTING_BY_KEY = {definition["key"]: definition for definition in SETTING_DEFINITIONS}


@router.get("/runtime", response_model=RuntimeSettingsResponse)
async def get_runtime_settings() -> RuntimeSettingsResponse:
    fields = []
    for definition in SETTING_DEFINITIONS:
        value = str(getattr(settings, definition["attr"], "") or "")
        secret = bool(definition.get("secret", False))
        fields.append(
            RuntimeSettingField(
                key=definition["key"],
                label=definition["label"],
                group=definition["group"],
                value="" if secret else value,
                configured=bool(value),
                secret=secret,
                help_url=definition.get("help_url", ""),
                placeholder=definition.get("placeholder", ""),
            )
        )
    warnings = [
        "设置会写入后端本地 .env，适合本地或可信私有部署；不要将服务直接暴露为公网管理后台。"
    ]
    return RuntimeSettingsResponse(fields=fields, warnings=warnings)


@router.post("/runtime", response_model=RuntimeSettingsResponse)
async def update_runtime_settings(payload: RuntimeSettingsUpdate) -> RuntimeSettingsResponse:
    unknown_keys = sorted(set(payload.values) - set(SETTING_BY_KEY))
    if unknown_keys:
        raise HTTPException(status_code=400, detail=f"Unsupported setting keys: {', '.join(unknown_keys)}")

    updates: dict[str, str] = {}
    for key, value in payload.values.items():
        definition = SETTING_BY_KEY[key]
        normalized = value.strip()
        if definition.get("secret") and not normalized:
            continue
        updates[key] = normalized

    if updates:
        _write_env_updates(ENV_PATH, updates)
        for key, value in updates.items():
            definition = SETTING_BY_KEY[key]
            setattr(settings, definition["attr"], _cast_setting_value(definition["attr"], value))

    return await get_runtime_settings()


def _write_env_updates(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        key = _parse_env_key(line)
        if key in updates:
            output.append(f"{key}={_format_env_value(updates[key])}")
            seen.add(key)
        else:
            output.append(line)

    missing = [key for key in updates if key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={_format_env_value(updates[key])}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _parse_env_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key if key in SETTING_BY_KEY else None


def _format_env_value(value: str) -> str:
    if not value:
        return ""
    if any(char.isspace() for char in value) or "#" in value or '"' in value or "'" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _cast_setting_value(attr: str, value: str) -> Any:
    current = getattr(settings, attr, "")
    if isinstance(current, bool):
        return value.lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except ValueError:
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError:
            return current
    return value
