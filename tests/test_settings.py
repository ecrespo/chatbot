import pytest

from reflex_chatbot.settings import PROVIDER_PRESETS, Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_ENABLED_PROVIDERS", raising=False)
    s = Settings.from_env()
    assert s.default_provider == "ollama"
    assert set(s.enabled_providers) == set(PROVIDER_PRESETS)


def test_provider_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_ENABLED_PROVIDERS", "ollama")
    monkeypatch.setenv("CUSTOM_BASE_URL", "http://vllm:8000/v1/")
    monkeypatch.setenv("CUSTOM_MODELS", "a, b")
    s = Settings.from_env()
    assert s.enabled_providers == ("custom", "ollama")
    custom = s.providers["custom"]
    assert custom.base_url == "http://vllm:8000/v1"
    assert custom.models == ("a", "b")


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError):
        Settings.from_env()
