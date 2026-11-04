import hashlib
import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from evidence.models import EvidenceSnapshot
from incidents.models import Incident
from investigations.models import InvestigationAttempt, InvestigationReport
from investigations.prompts import FACTS_SCHEMA, REPORT_SCHEMA, messages_for
from investigations.providers import ProviderFailure, profiles, public_profiles, select_provider
from investigations.service import run_investigation
from investigations.validation import snapshot_entries, validate_report


def event():
    return {
        "event_id": str(uuid4()),
        "source_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "source_name": "example.log",
        "source_lines": [1, 2],
        "occurred_at": "2026-10-29T08:00:00Z",
        "timestamp_quality": "explicit",
        "severity": "ERROR",
        "service": "payments",
        "message": "upstream gateway timeout",
    }


def report(eid):
    return {
        "schema_version": "1.0",
        "incident_summary": "A request timeout was observed; the cause is unconfirmed.",
        "observed_facts": [{"statement": "A timeout occurred.", "event_ids": [eid]}],
        "hypotheses": [
            {
                "title": "Downstream slowdown",
                "status": "plausible_unconfirmed",
                "supporting_event_ids": [eid],
                "contradicting_event_ids": [],
                "alternative_explanations": ["Network interruption"],
                "further_checks": ["Compare service latency"],
            }
        ],
        "suggested_actions": [
            {
                "action": "Review upstream health metrics",
                "safety": "review_only",
                "rationale_event_ids": [eid],
            }
        ],
        "limitations": ["No upstream metrics available"],
    }


@pytest.fixture
def record(db):
    user = get_user_model().objects.create_user(
        f"author-{uuid4()}@example.org", "sample-password-1234"
    )
    incident = Incident.objects.create(owner=user, title="Latency incident")
    entry = event()
    raw = json.dumps(
        {
            "selection_version": "1.0",
            "privacy_policy_version": "1.0",
            "incident_id": str(incident.id),
            "events": [entry],
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    snapshot = EvidenceSnapshot.objects.create(
        incident=incident,
        created_by=user,
        entries=[entry],
        sha256=hashlib.sha256(raw).hexdigest(),
        item_count=1,
        characters=len(entry["message"]),
        payload_bytes=len(raw),
        selection_version="1.0",
        privacy_policy_version="1.0",
        consent_accepted_at="2026-10-29T08:00:00Z",
    )
    client = Client()
    client.force_login(user)
    return incident, snapshot, entry, client


def payload(snapshot):
    return {
        "snapshot_id": str(snapshot.id),
        "provider": "groq",
        "model_id": "openai/gpt-oss-20b",
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "prompt_profile": "decomposed_verified",
        "transmission_consent": {"accepted": True, "snapshot_sha256": snapshot.sha256},
    }


def test_allowlisted_models_and_no_client_endpoints(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-secret")
    monkeypatch.setenv("GROQ_MODELS", "model-a,model-b")
    assert [entry["name"] for entry in public_profiles()][:2] == ["groq", "openai"]
    assert profiles()["groq"].models == ("model-a", "model-b")
    assert select_provider("groq", "model-a").endpoint.startswith("https://api.groq.com/")
    with pytest.raises(ProviderFailure, match="not allowed"):
        select_provider("groq", "attacker-supplied-model")


def test_two_prompt_methods_have_distinct_evidence_processing():
    entry = event()
    assert len(messages_for("few_shot", [entry])) == 4
    assert len(messages_for("extract", [entry])) == 2
    assert (
        messages_for(
            "decomposed_verified", [entry], observed={"observed_facts": [], "limitations": []}
        )[-1]["role"]
        == "user"
    )
    assert REPORT_SCHEMA["additionalProperties"] is False
    assert FACTS_SCHEMA["required"] == ["observed_facts", "limitations"]


def test_claim_validator_rejects_fabricated_references_and_secrets():
    entry = event()
    valid = report(entry["event_id"])
    assert validate_report(valid, [entry]) == valid
    valid["observed_facts"][0]["event_ids"] = [str(uuid4())]
    with pytest.raises(ProviderFailure, match="unsupported"):
        validate_report(valid, [entry])
    valid = report(entry["event_id"])
    valid["observed_facts"][0]["statement"] = "Authorization: Bearer sensitive-secret-123"
    with pytest.raises(ProviderFailure):
        validate_report(valid, [entry])


def test_decomposed_profile_calls_provider_twice_with_evidence():
    entry = event()
    answer = report(entry["event_id"])

    class FakeAdapter:
        def __init__(self):
            self.calls = []

        def complete(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {
                    "observed_facts": answer["observed_facts"],
                    "limitations": answer["limitations"],
                }, {"prompt_tokens": 11, "completion_tokens": 12}
            return answer, {"prompt_tokens": 21, "completion_tokens": 22}

    adapter = FakeAdapter()
    result, usage, version = run_investigation(
        provider=object(),
        model="model",
        entries=[entry],
        temperature=0.2,
        max_tokens=2048,
        prompt_profile="decomposed_verified",
        adapter=adapter,
    )
    assert result == answer
    assert len(adapter.calls) == 2
    assert usage == {"prompt_tokens": 32, "completion_tokens": 34}
    assert version == "1.0"


@pytest.mark.django_db
def test_snapshot_integrity_rejects_modified_evidence(record):
    _, snapshot, _, _ = record
    assert snapshot_entries(snapshot)
    snapshot.entries[0]["message"] = "modified content"
    with pytest.raises(ProviderFailure, match="integrity"):
        snapshot_entries(snapshot)


@pytest.mark.django_db
def test_no_consent_no_network_and_owner_isolation(record, monkeypatch):
    incident, snapshot, _, client = record
    url = f"/api/v1/incidents/{incident.id}/investigations"
    request = payload(snapshot)
    request["transmission_consent"]["accepted"] = False
    with patch("investigations.views.run_investigation") as call:
        assert client.post(url, request, content_type="application/json").status_code == 400
        call.assert_not_called()
    stranger = get_user_model().objects.create_user(
        f"other-{uuid4()}@example.org", "sample-password-1234"
    )
    client.force_login(stranger)
    with patch("investigations.views.run_investigation") as call:
        assert (
            client.post(url, payload(snapshot), content_type="application/json").status_code == 404
        )
        call.assert_not_called()


@pytest.mark.django_db
def test_success_persists_grounded_report_and_supports_history(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "mocked-provider-secret")
    url = f"/api/v1/incidents/{incident.id}/investigations"
    with patch(
        "investigations.views.run_investigation",
        return_value=(
            report(entry["event_id"]),
            {"prompt_tokens": 55, "completion_tokens": 65},
            "1.0",
        ),
    ) as call:
        response = client.post(url, payload(snapshot), content_type="application/json")
        assert response.status_code == 201
        call.assert_called_once()
    assert InvestigationReport.objects.filter(incident=incident).count() == 1
    assert InvestigationAttempt.objects.filter(incident=incident, status="succeeded").count() == 1
    data = response.json()
    assert data["report"]["observed_facts"][0]["event_ids"] == [entry["event_id"]]
    assert data["snapshot_sha256"] == snapshot.sha256
    assert len(client.get(url).json()) == 1
    assert client.get(f"{url}/{data['id']}").status_code == 200


@pytest.mark.django_db
def test_invalid_consent_hash_blocks_provider(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "mocked-provider-secret")
    data = payload(snapshot)
    data["transmission_consent"]["snapshot_sha256"] = "0" * 64
    with patch("investigations.views.run_investigation") as call:
        assert (
            client.post(
                f"/api/v1/incidents/{incident.id}/investigations",
                data,
                content_type="application/json",
            ).status_code
            == 409
        )
        call.assert_not_called()


def test_provider_adapter_validates_json_and_never_persists_key(monkeypatch):
    from investigations.providers import ChatCompletionsAdapter, ProviderProfile

    expected = report(str(uuid4()))

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _max_bytes):
            return json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(expected)}}
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 15},
                }
            ).encode("utf-8")

    requests = []

    def fake_open(request, *, timeout):
        requests.append(request)
        assert timeout <= 20
        return Response()

    monkeypatch.setattr("investigations.providers.urlopen", fake_open)
    client = ChatCompletionsAdapter(
        ProviderProfile(
            name="groq",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            api_key="secret-fixture",
            models=("test-model",),
            structured_mode="strict",
        )
    )
    result, usage = client.complete(
        model="test-model",
        messages=[{"role": "user", "content": "test"}],
        schema=REPORT_SCHEMA,
        temperature=0.2,
        max_tokens=512,
    )
    assert result == expected
    assert usage["prompt_tokens"] == 12
    assert len(requests) == 1
    sent = json.loads(requests[0].data)
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert "secret-fixture" not in requests[0].data.decode()
    assert requests[0].get_header("Authorization") == "Bearer secret-fixture"


@pytest.mark.django_db
def test_run_does_not_persist_when_provider_fails(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "mocked-provider-secret")
    with patch(
        "investigations.views.run_investigation",
        side_effect=ProviderFailure("rate_limited", "Provider limit reached", 429),
    ):
        response = client.post(
            f"/api/v1/incidents/{incident.id}/investigations",
            payload(snapshot),
            content_type="application/json",
        )
    assert response.status_code == 429
    assert InvestigationReport.objects.count() == 0
    assert (
        InvestigationAttempt.objects.filter(status="failed", failure_code="rate_limited").count()
        == 1
    )
