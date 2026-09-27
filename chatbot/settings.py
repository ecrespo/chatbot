"""Runtime configuration, read once from the environment (and `.env`).

Every LLM backend the chatbot supports speaks the OpenAI Chat Completions
protocol, so a provider is nothing more than a base URL, an optional API key,
a default model and a few optional extras. Each one is configured with its own
block of variables sharing a prefix::

    OLLAMA_BASE_URL=http://localhost:11434/v1
    OLLAMA_API_KEY=ollama
    OLLAMA_MODEL=llama3.2

`LLM_PROVIDER` picks the one the UI starts with; `LLM_ENABLED_PROVIDERS`
decides which ones appear in the provider picker.

API keys never leave the server: the Reflex state only stores the provider
*key* (``"ollama"``, ``"openrouter"`` …), and the secret is looked up here when
a request is made.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load `.env` from the project root. Variables already present in the process
# environment (docker `environment:`, `export FOO=…`) win over the file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(os.environ.get("CHATBOT_ENV_FILE") or _PROJECT_ROOT / ".env", override=False)

__all__ = [
    "PROVIDER_PRESETS",
    "Provider",
    "Settings",
    "get_provider",
    "settings",
]


# --------------------------------------------------------------------- #
# Small env helpers
# --------------------------------------------------------------------- #


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y", "si", "sí"}


def _env_float(name: str, default: float | None) -> float | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int | None) -> int | None:
    value = _env_float(name, None)
    return default if value is None else int(value)


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name, "")
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items if items else list(default or [])


def _env_json(name: str) -> dict[str, Any]:
    value = os.environ.get(name, "").strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object, got {type(parsed).__name__}")
    return parsed


# --------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Provider:
    """One OpenAI-compatible endpoint."""

    key: str
    label: str
    base_url: str
    api_key: str
    default_model: str = ""
    # Fixed model list; when empty the list comes from GET {base_url}/models.
    models: tuple[str, ...] = ()
    # Extra HTTP headers sent with every request (OpenRouter attribution, …).
    headers: dict[str, str] = field(default_factory=dict)
    # Extra JSON merged into every chat request body (provider-specific knobs).
    extra_body: dict[str, Any] = field(default_factory=dict)
    # Whether the provider needs an API key to work at all.
    requires_key: bool = False
    # Short hint shown when the provider cannot be reached.
    help: str = ""

    @property
    def is_configured(self) -> bool:
        """True when the provider has what it needs to be tried."""
        if not self.base_url:
            return False
        return bool(self.api_key) or not self.requires_key


# Defaults for every built-in provider. `env` is the variable prefix.
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "ollama": {
        "env": "OLLAMA",
        "label": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "default_model": "llama3.2",
        "help": "Arráncalo con `ollama serve` y descarga un modelo: `ollama pull llama3.2`.",
    },
    "lmstudio": {
        "env": "LMSTUDIO",
        "label": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "default_model": "",
        "help": "Abre LM Studio → Developer → Start Server y carga un modelo.",
    },
    "llamacpp": {
        "env": "LLAMACPP",
        "label": "llama.cpp",
        "base_url": "http://localhost:8080/v1",
        "api_key": "",
        "default_model": "",
        "help": "Ejecuta `llama-server -m modelo.gguf --jinja --port 8080` "
        "(`--jinja` habilita tool calling).",
    },
    "openrouter": {
        "env": "OPENROUTER",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "",
        "default_model": "openrouter/auto",
        "requires_key": True,
        "help": "Crea una clave en https://openrouter.ai/keys y define OPENROUTER_API_KEY.",
    },
    "omniroute": {
        "env": "OMNIROUTE",
        "label": "OmniRoute",
        "base_url": "http://localhost:20128/v1",
        "api_key": "",
        "default_model": "auto",
        "help": "Arranca el gateway (`npx omniroute` o su imagen Docker) en el puerto 20128.",
    },
    "custom": {
        "env": "CUSTOM",
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",
        "api_key": "",
        "default_model": "",
        "help": "Define CUSTOM_BASE_URL (y CUSTOM_API_KEY si el servidor la requiere).",
    },
}


def _build_provider(key: str, preset: dict[str, Any]) -> Provider:
    prefix = preset["env"]
    headers: dict[str, str] = {str(k): str(v) for k, v in _env_json(f"{prefix}_HEADERS").items()}
    if key == "openrouter":
        # Optional attribution headers, see https://openrouter.ai/docs/app-attribution
        referer = _env("OPENROUTER_HTTP_REFERER")
        title = _env("OPENROUTER_APP_TITLE")
        if referer:
            headers.setdefault("HTTP-Referer", referer)
        if title:
            headers.setdefault("X-Title", title)

    return Provider(
        key=key,
        label=_env(f"{prefix}_LABEL", preset["label"]),
        base_url=_env(f"{prefix}_BASE_URL", preset["base_url"]).rstrip("/"),
        api_key=_env(f"{prefix}_API_KEY", preset["api_key"]),
        default_model=_env(f"{prefix}_MODEL", preset["default_model"]),
        models=tuple(_env_list(f"{prefix}_MODELS")),
        headers=headers,
        extra_body=_env_json(f"{prefix}_EXTRA_BODY"),
        requires_key=bool(preset.get("requires_key", False)),
        help=preset.get("help", ""),
    )


# --------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------- #

DEFAULT_SYSTEM_PROMPT = (
    "You are a concise, friendly assistant embedded in a Reflex application. "
    "Answer in the user's language. Use markdown, and put code in fenced blocks "
    "with a language tag."
)


@dataclass(frozen=True)
class Settings:
    """Everything the app reads from the environment."""

    providers: dict[str, Provider]
    default_provider: str
    enabled_providers: tuple[str, ...]
    temperature: float
    max_tokens: int | None
    system_prompt: str
    enable_tools: bool
    show_reasoning: bool
    reasoning_effort: str
    max_tool_rounds: int
    request_timeout: float
    stream_interval: float
    app_title: str
    welcome_title: str
    welcome_subtitle: str

    @classmethod
    def from_env(cls) -> Settings:
        providers = {key: _build_provider(key, preset) for key, preset in PROVIDER_PRESETS.items()}

        enabled = [
            key
            for key in _env_list("LLM_ENABLED_PROVIDERS", list(PROVIDER_PRESETS))
            if key in providers
        ]
        default = _env("LLM_PROVIDER", "ollama").lower()
        if default not in providers:
            raise ValueError(f"LLM_PROVIDER={default!r} is not one of: {', '.join(providers)}")
        if default not in enabled:
            enabled.insert(0, default)

        return cls(
            providers=providers,
            default_provider=default,
            enabled_providers=tuple(enabled),
            temperature=_env_float("LLM_TEMPERATURE", 0.7) or 0.0,
            max_tokens=_env_int("LLM_MAX_TOKENS", None),
            system_prompt=_env("LLM_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            enable_tools=_env_bool("LLM_ENABLE_TOOLS", True),
            show_reasoning=_env_bool("LLM_SHOW_REASONING", True),
            reasoning_effort=_env("LLM_REASONING_EFFORT", "").lower(),
            max_tool_rounds=_env_int("LLM_MAX_TOOL_ROUNDS", 4) or 4,
            request_timeout=_env_float("LLM_REQUEST_TIMEOUT", 120.0) or 120.0,
            stream_interval=_env_float("CHAT_STREAM_INTERVAL", 0.05) or 0.0,
            app_title=_env("APP_TITLE", "Reflex Chatbot"),
            welcome_title=_env("APP_WELCOME_TITLE", "¿En qué puedo ayudarte?"),
            welcome_subtitle=_env(
                "APP_WELCOME_SUBTITLE",
                "Chat en streaming con Ollama, LM Studio, llama.cpp, OpenRouter u OmniRoute.",
            ),
        )


settings = Settings.from_env()


def get_provider(key: str) -> Provider:
    """The provider for ``key``, falling back to the default one."""
    return settings.providers.get(key) or settings.providers[settings.default_provider]
