"""Regression tests for opt-in, model-scoped OpenRouter reasoning policy."""

import json
from unittest.mock import patch

from investigations.providers import (
    ChatCompletionsAdapter,
    ProviderProfile,
    _reasoning_payload,
)

MODEL = "google/gemma-4-26b-a4b-it:free"


def profile(name="openrouter", model=MODEL):
    return ProviderProfile(
        name=name,
        endpoint="https://example.invalid/completions",
        api_key="dummy",
        models=(model,),
        structured_mode="json_object",
    )


def test_no_override_by_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_DISABLE_REASONING_MODELS", raising=False)
    payload = {"model": MODEL}
    assert _reasoning_payload(payload, profile(), MODEL) is payload


def test_opt_in_fixed_model_only(monkeypatch):
    monkeypatch.setenv("OPENROUTER_DISABLE_REASONING_MODELS", MODEL)
    payload = {"model": MODEL, "temperature": 0.2}
    result = _reasoning_payload(payload, profile(), MODEL)
    assert result["reasoning"] == {"enabled": False}
    assert result["model"] == MODEL
    assert "reasoning" not in payload


def test_no_effect_other_models_providers_or_dynamic_router(monkeypatch):
    monkeypatch.setenv("OPENROUTER_DISABLE_REASONING_MODELS", MODEL + ",openrouter/free")
    payload = {"model": MODEL}
    assert _reasoning_payload(payload, profile("groq"), MODEL) is payload
    assert (
        _reasoning_payload(payload, profile("openrouter", "openrouter/free"), "openrouter/free")
        is payload
    )
    assert _reasoning_payload(payload, profile("openrouter", "another/model"), MODEL) is payload


def test_http_request_contains_opt_in_and_keeps_json_mode(monkeypatch):
    monkeypatch.setenv("OPENROUTER_DISABLE_REASONING_MODELS", MODEL)
    data = {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    observed = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, n):
            return json.dumps(data).encode()

    def fake_urlopen(request, timeout):
        observed["timeout"] = timeout
        observed["body"] = json.loads(request.data)
        return FakeResponse()

    with patch("investigations.providers.urlopen", side_effect=fake_urlopen):
        answer, usage = ChatCompletionsAdapter(profile()).complete(
            model=MODEL,
            messages=[{"role": "user", "content": "{}"}],
            schema={"type": "object"},
            temperature=0.2,
            max_tokens=4096,
        )

    assert answer == {"ok": True}
    assert usage["completion_tokens"] == 2
    assert observed["body"]["reasoning"] == {"enabled": False}
    assert observed["body"]["response_format"] == {"type": "json_object"}
    assert observed["body"]["max_tokens"] == 4096
    assert observed["timeout"] == 16
