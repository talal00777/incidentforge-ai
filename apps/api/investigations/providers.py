"""Server-owned OpenAI-compatible chat adapters, with no user-supplied endpoints."""

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    endpoint: str
    api_key: str
    models: tuple[str, ...]
    structured_mode: str


class ProviderFailure(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def profiles() -> dict[str, ProviderProfile]:
    """The operator, not the browser, selects allowed endpoints and model IDs."""
    definitions = (
        (
            "groq",
            "https://api.groq.com/openai/v1/chat/completions",
            "GROQ_API_KEY",
            "GROQ_MODELS",
            "openai/gpt-oss-20b,openai/gpt-oss-120b",
            "strict",
        ),
        (
            "openai",
            "https://api.openai.com/v1/chat/completions",
            "OPENAI_API_KEY",
            "OPENAI_MODELS",
            "gpt-4o-mini",
            "strict",
        ),
        (
            "openrouter",
            "https://openrouter.ai/api/v1/chat/completions",
            "OPENROUTER_API_KEY",
            "OPENROUTER_MODELS",
            "",
            "json_object",
        ),
    )
    return {
        name: ProviderProfile(
            name=name,
            endpoint=endpoint,
            api_key=os.getenv(key, "").strip(),
            models=tuple(
                item
                for part in os.getenv(model_env, default_models).split(",")
                if (item := part.strip())
            ),
            structured_mode=mode,
        )
        for name, endpoint, key, model_env, default_models, mode in definitions
    }


def public_profiles() -> list[dict]:
    return [
        {
            "name": item.name,
            "models": list(item.models),
            "available": bool(item.api_key and item.models),
        }
        for item in profiles().values()
    ]


def select_provider(name: str, model_id: str) -> ProviderProfile:
    profile = profiles().get(name)
    if profile is None or model_id not in profile.models:
        raise ProviderFailure(
            "unsupported_model", "Selected provider or model is not allowed.", 400
        )
    if not profile.api_key:
        raise ProviderFailure("provider_unavailable", "This provider is not configured.", 503)
    return profile


def _json_mode_messages(messages: list[dict], schema: dict) -> list[dict]:
    """Convey the expected schema to JSON-object providers without mutating inputs."""
    guidance = (
        "Return only a JSON object matching the following JSON Schema exactly. "
        "Include all required properties, including empty arrays when necessary. "
        "Do not add properties outside the schema, alter enum values, or include Markdown.\n"
        "JSON Schema: " + json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
    )
    result = [dict(message) for message in messages]
    if result and result[0].get("role") == "system" and isinstance(result[0].get("content"), str):
        result[0]["content"] += "\n\n" + guidance
    else:
        result.insert(0, {"role": "system", "content": guidance})
    return result


def _reasoning_payload(payload: dict, profile: ProviderProfile, model: str) -> dict:
    """Opt-in, model-specific reasoning override for an approved OpenRouter model."""
    if profile.name != "openrouter" or model == "openrouter/free":
        return payload
    configured = {
        item.strip()
        for item in os.getenv("OPENROUTER_DISABLE_REASONING_MODELS", "").split(",")
        if item.strip()
    }
    if model not in configured or model not in profile.models:
        return payload
    return {**payload, "reasoning": {"enabled": False}}


class ChatCompletionsAdapter:
    """Network boundary; replaceable with fake adapter in application tests."""

    def __init__(self, profile: ProviderProfile):
        self.profile = profile

    def complete(
        self, *, model: str, messages: list[dict], schema: dict, temperature: float, max_tokens: int
    ) -> tuple[dict, dict]:
        response_format = (
            {
                "type": "json_schema",
                "json_schema": {"name": "incident_investigation", "strict": True, "schema": schema},
            }
            if self.profile.structured_mode == "strict"
            else {"type": "json_object"}
        )
        request_messages = (
            messages
            if self.profile.structured_mode == "strict"
            else _json_mode_messages(messages, schema)
        )
        payload = json.dumps(
            _reasoning_payload(
                {
                    "model": model,
                    "messages": request_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": response_format,
                    "stream": False,
                },
                self.profile,
                model,
            )
        ).encode("utf-8")
        endpoint = urlsplit(self.profile.endpoint)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
        ):
            raise ProviderFailure(
                "provider_configuration",
                "AI provider endpoint must use HTTPS.",
                503,
            )
        request = Request(  # noqa: S310 - validated HTTPS endpoint from backend configuration
            self.profile.endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.profile.api_key}",
            },
        )
        try:
            with urlopen(request, timeout=16) as response:  # noqa: S310 - fixed operator-owned HTTPS endpoints
                if response.status != 200:
                    raise ProviderFailure(
                        "provider_error", "The AI provider returned an unexpected response."
                    )
                raw = response.read(256_001)
                if len(raw) > 256_000:
                    raise ProviderFailure(
                        "provider_response", "The AI provider response was too large."
                    )
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderFailure(
                    "rate_limited", "Provider rate limit reached. Try again later.", 429
                ) from exc
            if exc.code in (401, 403):
                raise ProviderFailure(
                    "provider_auth", "AI provider credentials were rejected.", 503
                ) from exc
            if exc.code in (400, 404, 422):
                raise ProviderFailure(
                    "provider_rejected",
                    "Provider rejected this model or request configuration.",
                    422,
                ) from exc
            raise ProviderFailure(
                "provider_error", "The AI provider is temporarily unavailable."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderFailure(
                "provider_unreachable", "Unable to reach the AI provider.", 503
            ) from exc
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ProviderFailure(
                "invalid_response", "The provider returned an invalid response envelope.", 502
            ) from exc
        if not isinstance(data, dict):
            raise ProviderFailure(
                "invalid_response", "The provider returned an unexpected response format.", 502
            )
        if data.get("error") is not None:
            raise ProviderFailure(
                "provider_error", "The provider reported a generation failure.", 502
            )
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderFailure(
                "invalid_response", "The provider returned no completion choice.", 502
            )
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ProviderFailure(
                "output_truncated",
                "The model exhausted its output-token budget before completing. "
                "Try 4096 tokens or a different model.",
                502,
            )
        if finish_reason == "content_filter":
            raise ProviderFailure(
                "content_filtered", "The model response was filtered by the provider.", 502
            )
        if finish_reason != "stop":
            raise ProviderFailure(
                "provider_incomplete", "The provider did not complete a text response.", 502
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderFailure(
                "invalid_response", "The provider returned no assistant message.", 502
            )
        if message.get("refusal"):
            raise ProviderFailure(
                "provider_refusal", "The model declined to produce an investigation.", 502
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderFailure(
                "empty_response",
                "The model returned no final JSON content. Try a model supporting JSON output.",
                502,
            )
        try:
            answer = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise ProviderFailure(
                "invalid_response",
                "The model returned malformed JSON despite the JSON-output request.",
                502,
            ) from exc
        if not isinstance(answer, dict):
            raise ProviderFailure(
                "invalid_response", "The model returned JSON that was not an object.", 502
            )
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        return answer, usage
