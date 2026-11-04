"""No-network regression tests for provider response decoding and safe errors."""

import json

import pytest

from investigations.providers import ChatCompletionsAdapter, ProviderFailure, ProviderProfile


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return self.payload[:count]


def request(monkeypatch, response):
    raw = json.dumps(response).encode() if not isinstance(response, bytes) else response
    captured = []

    def fake_urlopen(req, timeout):
        captured.append(json.loads(req.data))
        return Response(raw)

    monkeypatch.setattr("investigations.providers.urlopen", fake_urlopen)
    profile = ProviderProfile(
        "openrouter", "https://example.invalid/chat", "test-key", ("test-model",), "json_object"
    )
    adapter = ChatCompletionsAdapter(profile)

    def call():
        return adapter.complete(
            model="test-model",
            messages=[{"role": "user", "content": "synthetic test"}],
            schema={"type": "object"},
            temperature=0.2,
            max_tokens=2048,
        )

    return call, captured


def envelope(*, finish="stop", content='{"ok":true}', usage=None):
    return {
        "choices": [
            {"finish_reason": finish, "message": {"role": "assistant", "content": content}}
        ],
        "usage": usage or {"completion_tokens": 3},
    }


def test_valid_json_is_unchanged(monkeypatch):
    call, captured = request(monkeypatch, envelope())
    data, usage = call()
    assert data == {"ok": True}
    assert usage == {"completion_tokens": 3}
    assert captured[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (envelope(finish="length", content=""), "output_truncated"),
        (envelope(finish="content_filter"), "content_filtered"),
        (envelope(finish="error"), "provider_incomplete"),
        (envelope(content=""), "empty_response"),
        (envelope(content=None), "empty_response"),
        (envelope(content="this is a SECRET-TEST-VALUE, not JSON"), "invalid_response"),
        (envelope(content="[]"), "invalid_response"),
        ({"choices": []}, "invalid_response"),
        ({"error": {"message": "SECRET-TEST-VALUE"}, "choices": []}, "provider_error"),
        (b"<!DOCTYPE html>SECRET-TEST-VALUE", "invalid_response"),
    ],
)
def test_safe_response_failures(monkeypatch, body, expected):
    call, _ = request(monkeypatch, body)
    with pytest.raises(ProviderFailure) as exc:
        call()
    assert exc.value.code == expected
    assert exc.value.status == 502
    assert "SECRET-TEST-VALUE" not in exc.value.message


def test_refusal_is_classified(monkeypatch):
    payload = envelope()
    payload["choices"][0]["message"]["refusal"] = "SECRET-TEST-VALUE"
    call, _ = request(monkeypatch, payload)
    with pytest.raises(ProviderFailure) as exc:
        call()
    assert exc.value.code == "provider_refusal"
    assert "SECRET-TEST-VALUE" not in exc.value.message


def test_missing_message_is_classified(monkeypatch):
    payload = envelope()
    del payload["choices"][0]["message"]
    call, _ = request(monkeypatch, payload)
    with pytest.raises(ProviderFailure) as exc:
        call()
    assert exc.value.code == "invalid_response"
