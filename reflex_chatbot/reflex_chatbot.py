"""Reflex chatbot built on reflex-assistant-ui.

The page is a single streaming chat. The toolbar picks the LLM provider
(Ollama, LM Studio, llama.cpp, OpenRouter, OmniRoute or any OpenAI-compatible
server) and the model; defaults come from `.env` — see `.env.example`.
"""

from __future__ import annotations

import reflex as rx
from reflex_assistant_ui import assistant_ui

from .settings import settings
from .state import ChatState

WELCOME_SUGGESTIONS = [
    {
        "prompt": "¿Qué hora es en Caracas y en Madrid?",
        "title": "¿Qué hora es?",
        "label": "usa una herramienta",
    },
    {
        "prompt": "Calcula (18 * 7) / 3 y explica los pasos.",
        "title": "Haz un cálculo",
        "label": "usa una herramienta",
    },
    {"prompt": "Escribe un generador async en Python que emita tokens.", "title": "Escribe código"},
    {
        "prompt": "Resume las diferencias entre Ollama, LM Studio y llama.cpp.",
        "title": "Compara herramientas",
    },
]


def _labelled(label: str, control: rx.Component) -> rx.Component:
    return rx.hstack(
        control,
        rx.text(label, size="1", color_scheme="gray"),
        spacing="1",
        align="center",
    )


def header() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.icon("bot", size=20),
            rx.heading(settings.app_title, size="4", white_space="nowrap"),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        rx.tooltip(
            rx.badge(
                ChatState.status_label,
                color_scheme=ChatState.status_color,
                variant="soft",
                size="2",
            ),
            content=rx.cond(
                ChatState.connection_error != "",
                ChatState.connection_error,
                ChatState.base_url,
            ),
        ),
        rx.color_mode.button(),
        width="100%",
        padding="0.6rem 1rem",
        border_bottom="1px solid var(--gray-a5)",
        align="center",
        spacing="3",
    )


def toolbar() -> rx.Component:
    return rx.hstack(
        rx.select(
            ChatState.provider_labels,
            value=ChatState.provider_label,
            on_change=ChatState.set_provider_label,
            size="2",
            width="13rem",
            aria_label="Proveedor",
        ),
        rx.cond(
            ChatState.models.length() > 0,
            rx.select(
                ChatState.models,
                value=ChatState.model,
                on_change=ChatState.set_model,
                size="2",
                width="18rem",
                aria_label="Modelo",
            ),
            rx.text("sin modelos", size="2", color_scheme="gray"),
        ),
        rx.hstack(
            rx.text("temp", size="1", color_scheme="gray"),
            rx.text(ChatState.temperature.to_string(), size="1", weight="medium"),
            rx.slider(
                default_value=[int(settings.temperature * 100)],
                min=0,
                max=150,
                step=5,
                on_change=ChatState.set_temperature,
                width="6rem",
            ),
            spacing="2",
            align="center",
        ),
        _labelled(
            "herramientas",
            rx.switch(checked=ChatState.enable_tools, on_change=ChatState.toggle_tools, size="1"),
        ),
        _labelled(
            "razonamiento",
            rx.switch(
                checked=ChatState.show_reasoning, on_change=ChatState.toggle_reasoning, size="1"
            ),
        ),
        rx.spacer(),
        rx.button(
            rx.icon("refresh-cw", size=14),
            "Modelos",
            on_click=ChatState.refresh_models,
            variant="soft",
            size="2",
        ),
        rx.button(
            rx.icon("plus", size=14),
            "Nuevo chat",
            on_click=ChatState.new_conversation,
            variant="soft",
            size="2",
        ),
        width="100%",
        padding="0.5rem 1rem",
        border_bottom="1px solid var(--gray-a5)",
        align="center",
        spacing="3",
        wrap="wrap",
    )


def offline_banner() -> rx.Component:
    return rx.cond(
        ChatState.connection == "offline",
        rx.callout(
            rx.vstack(
                rx.text(
                    rx.text.strong(ChatState.provider_label),
                    " no responde en ",
                    rx.code(ChatState.base_url),
                    ": ",
                    ChatState.connection_error,
                ),
                rx.text(ChatState.provider_help, size="1"),
                spacing="1",
                align="start",
            ),
            icon="triangle_alert",
            color_scheme="amber",
            size="1",
            margin="0.5rem 1rem 0",
        ),
    )


@rx.page(route="/", title=settings.app_title, on_load=ChatState.refresh_models)
def index() -> rx.Component:
    return rx.vstack(
        header(),
        toolbar(),
        offline_banner(),
        rx.box(
            assistant_ui.chat(
                messages=ChatState.messages,
                head_id=ChatState.head_id,
                is_running=ChatState.is_running,
                suggestions=ChatState.suggestions,
                on_new=ChatState.handle_new,
                on_edit=ChatState.handle_edit,
                on_reload=ChatState.handle_reload,
                on_cancel=ChatState.handle_cancel,
                on_delete=ChatState.handle_delete,
                on_branch_change=ChatState.handle_branch_change,
                on_feedback=ChatState.handle_feedback,
                enable_feedback=True,
                show_feedback=True,
                welcome_title=settings.welcome_title,
                welcome_subtitle=settings.welcome_subtitle,
                welcome_suggestions=WELCOME_SUGGESTIONS,
                placeholder="Escribe un mensaje…",
                height="100%",
            ),
            width="100%",
            flex="1 1 auto",
            min_height="0",
        ),
        width="100%",
        height="100vh",
        spacing="0",
    )


# Radix theme configured through RadixThemesPlugin in rxconfig.py.
app = rx.App()
