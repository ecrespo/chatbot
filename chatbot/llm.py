"""Streaming chat against any OpenAI-compatible endpoint.

Ollama, LM Studio, llama.cpp (`llama-server`), OpenRouter and OmniRoute all
expose ``POST /v1/chat/completions`` and ``GET /v1/models``, so a single client
covers them. This module:

* lists the models a provider offers;
* streams a reply, yielding chunks in the shape ``AssistantUIState`` expects
  (``str`` text deltas, ``{"reasoning": …}``, ``{"tool_call": …}``);
* runs the tool-calling loop;
* normalises reasoning, which providers report differently: a
  ``reasoning_content`` field (llama.cpp, LM Studio, DeepSeek), a ``reasoning``
  field (OpenRouter, Ollama) or inline ``<think>…</think>`` tags in the text.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from reflex_assistant_ui import tool_call_part

from .settings import Provider, settings
from .tools import TOOL_SCHEMAS, run_tool

__all__ = ["ThinkTagSplitter", "describe_error", "list_models", "stream_chat"]

# (provider, model) pairs that rejected a feature; asked once, then left alone.
_NO_TOOLS: set[tuple[str, str]] = set()
_NO_REASONING_EFFORT: set[tuple[str, str]] = set()

_clients: dict[str, AsyncOpenAI] = {}


def _client(provider: Provider) -> AsyncOpenAI:
    """One cached client per provider."""
    client = _clients.get(provider.key)
    if client is None:
        client = AsyncOpenAI(
            base_url=provider.base_url,
            # The SDK insists on a key; local servers ignore it.
            api_key=provider.api_key or "not-needed",
            default_headers=provider.headers or None,
            timeout=httpx.Timeout(settings.request_timeout, connect=10.0),
            max_retries=1,
        )
        _clients[provider.key] = client
    return client


def describe_error(exc: BaseException, provider: Provider | None = None) -> str:
    """A short, human explanation of a failed request."""
    if isinstance(exc, APITimeoutError):
        detail = "la petición excedió el tiempo de espera (LLM_REQUEST_TIMEOUT)"
    elif isinstance(exc, APIConnectionError):
        target = provider.base_url if provider else "el servidor"
        detail = f"no se pudo conectar con {target}"
    elif isinstance(exc, APIStatusError):
        message = ""
        try:
            body = exc.response.json()
            error = body.get("error", body) if isinstance(body, dict) else body
            message = error.get("message", "") if isinstance(error, dict) else str(error)
        except Exception:  # noqa: BLE001 - fall back to the SDK's message
            message = str(exc)
        detail = f"HTTP {exc.status_code}: {message or exc.message}"
    else:
        detail = f"{type(exc).__name__}: {exc}"
    return detail[:500]


async def list_models(provider: Provider) -> tuple[list[str], str]:
    """``(models, error)``. A fixed ``*_MODELS`` list wins over discovery."""
    if provider.models:
        return list(provider.models), ""
    if not provider.is_configured:
        return [], "no configurado (falta la URL base o la API key)"
    try:
        page = await _client(provider).models.list()
        models = sorted({m.id for m in page.data if getattr(m, "id", None)})
    except Exception as exc:  # noqa: BLE001 - the UI shows the reason
        return [], describe_error(exc, provider)
    return models, ""


# --------------------------------------------------------------------- #
# <think> tags
# --------------------------------------------------------------------- #


class ThinkTagSplitter:
    """Split streamed text into text and reasoning around ``<think>`` tags.

    Tags may be cut across chunks, so a possible partial tag at the end of a
    chunk is held back until the next one arrives.
    """

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._thinking = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        self._buffer += text
        out: list[tuple[str, str]] = []
        while self._buffer:
            tag = self.CLOSE if self._thinking else self.OPEN
            kind = "reasoning" if self._thinking else "text"
            index = self._buffer.find(tag)
            if index >= 0:
                if index:
                    out.append((kind, self._buffer[:index]))
                self._buffer = self._buffer[index + len(tag) :]
                self._thinking = not self._thinking
                continue
            # Keep back a suffix that could be the start of the tag.
            keep = 0
            for size in range(min(len(tag) - 1, len(self._buffer)), 0, -1):
                if tag.startswith(self._buffer[-size:]):
                    keep = size
                    break
            emit = self._buffer[: len(self._buffer) - keep]
            if emit:
                out.append((kind, emit))
            self._buffer = self._buffer[len(self._buffer) - keep :]
            break
        return out

    def flush(self) -> list[tuple[str, str]]:
        rest, self._buffer = self._buffer, ""
        return [("reasoning" if self._thinking else "text", rest)] if rest else []


def _reasoning_delta(delta: Any) -> str:
    """Reasoning text from a streamed delta, whatever the provider calls it."""
    for name in ("reasoning_content", "reasoning", "thinking"):
        value = getattr(delta, name, None)
        if value is None and getattr(delta, "model_extra", None):
            value = delta.model_extra.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


# --------------------------------------------------------------------- #
# Streaming loop
# --------------------------------------------------------------------- #


async def stream_chat(
    provider: Provider,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float | None = None,
    use_tools: bool = True,
    reasoning_effort: str = "",
    is_cancelled: Callable[[], bool] = lambda: False,
) -> AsyncIterator[Any]:
    """Stream the reply to ``messages``, running tools as the model asks."""
    client = _client(provider)
    conversation = list(messages)
    feature_key = (provider.key, model)

    for _round in range(settings.max_tool_rounds):
        with_tools = use_tools and feature_key not in _NO_TOOLS
        with_effort = bool(reasoning_effort) and feature_key not in _NO_REASONING_EFFORT

        request: dict[str, Any] = {"model": model, "messages": conversation, "stream": True}
        if temperature is not None:
            request["temperature"] = temperature
        if settings.max_tokens:
            request["max_tokens"] = settings.max_tokens
        if with_tools:
            request["tools"] = TOOL_SCHEMAS
        if with_effort:
            request["reasoning_effort"] = reasoning_effort
        if provider.extra_body:
            request["extra_body"] = provider.extra_body

        text = ""
        calls: dict[int, dict[str, str]] = {}
        splitter = ThinkTagSplitter()

        try:
            stream = await client.chat.completions.create(**request)
            async with stream:
                async for chunk in stream:
                    if is_cancelled():
                        return
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue

                    reasoning = _reasoning_delta(delta)
                    if reasoning:
                        yield {"reasoning": reasoning}

                    if delta.content:
                        for kind, piece in splitter.feed(delta.content):
                            if kind == "reasoning":
                                yield {"reasoning": piece}
                            else:
                                text += piece
                                yield piece

                    for call in delta.tool_calls or []:
                        index = call.index if call.index is not None else len(calls)
                        slot = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if call.id:
                            slot["id"] = call.id
                        if call.function is not None:
                            if call.function.name:
                                slot["name"] += call.function.name
                            if call.function.arguments:
                                slot["arguments"] += call.function.arguments
        except APIStatusError as exc:
            detail = describe_error(exc, provider).lower()
            # Models without function calling or a reasoning knob reject the
            # request outright; remember it and retry this turn without it.
            if with_tools and exc.status_code in (400, 404, 422, 500) and "tool" in detail:
                _NO_TOOLS.add(feature_key)
                continue
            if with_effort and exc.status_code in (400, 422) and "reasoning" in detail:
                _NO_REASONING_EFFORT.add(feature_key)
                continue
            yield _failure(exc, provider, model)
            return
        except Exception as exc:  # noqa: BLE001 - surfaced in the thread
            yield _failure(exc, provider, model)
            return

        for kind, piece in splitter.flush():
            if kind == "reasoning":
                yield {"reasoning": piece}
            else:
                text += piece
                yield piece

        if not calls:
            return

        # Replay the model's tool calls, run them, and hand the results back.
        ordered = [calls[i] for i in sorted(calls)]
        for number, call in enumerate(ordered):
            call["id"] = call["id"] or f"call_{_round}_{number}"
        conversation.append(
            {
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"] or "{}"},
                    }
                    for call in ordered
                ],
            }
        )

        for call in ordered:
            try:
                args = json.loads(call["arguments"]) if call["arguments"].strip() else {}
                if not isinstance(args, dict):
                    args = {"value": args}
            except json.JSONDecodeError:
                args = {}
            part = tool_call_part(call["name"], args, tool_call_id=call["id"])
            yield {"tool_call": part}

            result = await run_tool(call["name"], args)
            yield {
                "tool_call": {
                    **part,
                    "result": result,
                    "is_error": isinstance(result, dict) and "error" in result,
                }
            }
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
        # A separator so text after the tools does not glue onto text before.
        text = ""

    yield "\n\n> Se detuvo tras demasiadas rondas de herramientas."


def _failure(exc: BaseException, provider: Provider, model: str) -> str:
    """Markdown shown in the thread when the request fails."""
    lines = [
        f"\n\n> **No se pudo obtener respuesta de {provider.label}** "
        f"(`{model or 'sin modelo'}` en `{provider.base_url}`).",
        ">",
        f"> {describe_error(exc, provider)}",
    ]
    if provider.help:
        lines += [">", f"> {provider.help}"]
    return "\n".join(lines)
