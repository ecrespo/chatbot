"""Chat state: provider/model selection plus the assistant-ui conversation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import reflex as rx
from reflex_assistant_ui import AssistantUIState

from . import llm
from .settings import get_provider, settings


def _provider_options() -> list[dict[str, str]]:
    return [
        {"key": key, "label": settings.providers[key].label} for key in settings.enabled_providers
    ]


class ChatState(AssistantUIState, rx.State):
    """Everything the chat page needs.

    Only non-secret values live here — Reflex state is mirrored to the browser.
    The API key for the selected provider is resolved server-side in ``llm``.
    """

    # Provider / model selection
    provider: str = settings.default_provider
    providers: list[dict[str, str]] = _provider_options()
    models: list[str] = []
    model: str = ""
    # "checking" | "ready" | "offline"
    connection: str = "checking"
    connection_error: str = ""

    # Generation options (defaults from .env, adjustable in the UI)
    temperature: float = settings.temperature
    enable_tools: bool = settings.enable_tools
    show_reasoning: bool = settings.show_reasoning

    system_prompt: str = settings.system_prompt
    stream_interval: float = settings.stream_interval

    # ----------------------------------------------------------------- #
    # Derived vars
    # ----------------------------------------------------------------- #

    @rx.var
    def provider_label(self) -> str:
        return get_provider(self.provider).label

    @rx.var
    def provider_labels(self) -> list[str]:
        return [p["label"] for p in self.providers]

    @rx.var
    def base_url(self) -> str:
        return get_provider(self.provider).base_url

    @rx.var
    def status_label(self) -> str:
        if self.connection == "checking":
            return f"Conectando con {self.provider_label}…"
        if self.connection == "ready":
            return f"{self.provider_label} · {self.model or 'sin modelo'}"
        return f"{self.provider_label} sin conexión"

    @rx.var
    def status_color(self) -> str:
        return {"ready": "green", "checking": "gray"}.get(self.connection, "red")

    @rx.var
    def provider_help(self) -> str:
        return get_provider(self.provider).help

    # ----------------------------------------------------------------- #
    # Events
    # ----------------------------------------------------------------- #

    @rx.event
    async def refresh_models(self):
        """Ask the current provider which models it serves."""
        provider = get_provider(self.provider)
        self.connection = "checking"
        yield
        models, error = await llm.list_models(provider)

        # A configured default model is always offered, even when discovery
        # fails or the provider (e.g. OpenRouter) lists hundreds of ids.
        default = provider.default_model
        if default and not any(_same_model(default, name) for name in models):
            models = [default, *models]

        self.models = models
        self.connection_error = error
        self.connection = "offline" if error else "ready"

        if self.model not in models:
            self.model = _pick_default(provider.default_model, models)

    @rx.event
    async def set_provider_label(self, label: str):
        """Provider picker handler (the select works on labels)."""
        key = next((p["key"] for p in self.providers if p["label"] == label), None)
        if key is None or key == self.provider:
            return
        self.provider = key
        self.model = ""
        self.models = []
        return ChatState.refresh_models

    @rx.event
    def set_model(self, model: str):
        self.model = model

    @rx.event
    def set_temperature(self, value: list[int | float]):
        """Slider handler: Reflex sends a one-element list."""
        self.temperature = round(float(value[0]) / 100, 2)

    @rx.event
    def toggle_tools(self, value: bool):
        self.enable_tools = value

    @rx.event
    def toggle_reasoning(self, value: bool):
        self.show_reasoning = value

    @rx.event
    def new_conversation(self):
        self.reset_chat()

    # ----------------------------------------------------------------- #
    # Reply generation (called by AssistantUIState)
    # ----------------------------------------------------------------- #

    async def _respond(self, history: list[dict[str, Any]]) -> AsyncIterator[Any]:
        provider = get_provider(self.provider)
        if not self.model:
            yield (
                f"> **{provider.label} no tiene un modelo seleccionado.** "
                f"{self.connection_error or ''}\n>\n> {provider.help}"
            )
            return

        async for chunk in llm.stream_chat(
            provider,
            self.model,
            history,
            temperature=self.temperature,
            use_tools=self.enable_tools,
            reasoning_effort=settings.reasoning_effort,
            is_cancelled=lambda: self._cancel_requested,
        ):
            if not self.show_reasoning and isinstance(chunk, dict) and "reasoning" in chunk:
                continue
            yield chunk


def _pick_default(preferred: str, models: list[str]) -> str:
    """Configured model if present (tag-insensitive), else the first one."""
    if not models:
        return preferred
    if preferred:
        if preferred in models:
            return preferred
        for name in models:
            if _same_model(preferred, name):
                return name
    return models[0]


def _same_model(a: str, b: str) -> bool:
    """Ollama-style names match regardless of the ``:latest`` tag."""
    strip = lambda name: name.removesuffix(":latest")  # noqa: E731
    return a == b or strip(a) == strip(b)
