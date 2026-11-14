"""Job authorization, state audit, recovery, and safe diagnostics."""

import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from investigations.jobs import _claim, _finish, reconcile_investigations
from investigations.models import AIInvestigationJob, InvestigationReport
from investigations.tests.test_async_jobs import create_job
from investigations.tests.test_investigations_m42 import record as record
from investigations.tests.test_investigations_m42 import report


@pytest.mark.django_db
def test_job_responses_are_private_including_errors(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    assert created.status_code == 202
    path = created["Location"]
    for response in (
        created,
        client.get(path),
        client.get(f"/api/v1/incidents/{incident.id}/ai-runs"),
        client.post(path + "/cancel"),
        client.post(path + "/cancel"),
    ):
        assert response["Cache-Control"] == "private, no-store"
    client.logout()
    assert client.get(path)["Cache-Control"] == "private, no-store"
    assert client.get(path).status_code in (401, 403)


@pytest.mark.django_db
def test_job_access_obeys_current_incident_ownership(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    assert created.status_code == 202
    path = created["Location"]
    other = get_user_model().objects.create_user(
        f"operator-{uuid4()}@example.org", "valid-test-password-527"
    )
    client.force_login(other)
    assert client.get(path).status_code == 404
    assert client.post(path + "/cancel").status_code == 404
    assert client.get(f"/api/v1/incidents/{incident.id}/ai-runs").status_code == 404
    assert create_job(client, incident, snapshot).status_code == 404
    incident.owner = other
    incident.save(update_fields=["owner"])
    client.force_login(snapshot.created_by)
    assert client.get(path).status_code == 404
    client.force_login(other)
    assert client.get(path).status_code == 404
    assert AIInvestigationJob.objects.count() == 1


@pytest.mark.django_db
def test_state_history_is_append_only_and_excludes_evidence(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot, key="reviewed-run-123456")
    job = AIInvestigationJob.objects.get(pk=created.json()["job_id"])
    assert job.events.count() == 1
    assert job.events.get().action == "submitted"
    assert job.events.get().actor_id == incident.owner_id
    assert create_job(client, incident, snapshot, key="reviewed-run-123456").status_code == 202
    assert job.events.count() == 1
    token = _claim(str(job.pk))
    assert token
    assert list(job.events.values_list("action", flat=True)) == ["submitted", "claimed"]
    assert client.post(created["Location"] + "/cancel").status_code == 202
    _finish(
        str(job.pk),
        token,
        output=(
            {"schema_version": "1.0"},
            {"prompt_tokens": 1, "completion_tokens": 1},
            "1.0",
        ),
    )
    assert not InvestigationReport.objects.filter(attempt=job.attempt).exists()
    assert list(job.events.values_list("action", flat=True)) == [
        "submitted",
        "claimed",
        "cancel_requested",
        "cancelled",
    ]
    assert job.events.get(action="cancel_requested").actor_id == incident.owner_id
    serialized = json.dumps(list(job.events.values()), default=str)
    assert entry["message"] not in serialized
    assert "configured-provider-token" not in serialized
    assert job.idempotency_key not in serialized


@pytest.mark.django_db
def test_reconcile_recovers_missing_lease_and_rejects_old_claim(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    job_id = created.json()["job_id"]
    token = _claim(job_id)
    AIInvestigationJob.objects.filter(pk=job_id).update(lease_until=None)
    with patch("investigations.jobs.enqueue_job") as enqueue:
        reconcile_investigations.run()
        enqueue.assert_called_with(job_id)
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "retry_wait"
    assert job.attempt_count == 1
    assert job.executions.get(number=1).state == "interrupted"
    assert list(job.events.values_list("action", flat=True)) == [
        "submitted",
        "claimed",
        "interrupted",
        "retry_scheduled",
    ]
    _finish(job_id, token, output=({"schema_version": "1.0"}, {}, "1.0"))
    assert not InvestigationReport.objects.filter(attempt=job.attempt).exists()


@pytest.mark.django_db
def test_reconcile_finalizes_cancelling_job_with_missing_lease(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    job_id = created.json()["job_id"]
    _claim(job_id)
    assert client.post(created["Location"] + "/cancel").status_code == 202
    AIInvestigationJob.objects.filter(pk=job_id).update(lease_until=None)
    reconcile_investigations.run()
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "cancelled"
    assert job.cancel_requested
    assert list(job.events.values_list("action", flat=True)) == [
        "submitted",
        "claimed",
        "cancel_requested",
        "interrupted",
        "cancelled",
    ]


@pytest.mark.django_db
def test_safe_operator_summary_excludes_user_and_job_identifiers(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    job = AIInvestigationJob.objects.get(pk=created.json()["job_id"])
    output = StringIO()
    call_command("inspect_ai_jobs", "--json", stdout=output)
    data = json.loads(output.getvalue())
    assert data["states"]["queued"] == 1
    assert data["due_pending"] == 1
    assert data["missing_leases"] == 0
    assert data["expired_leases"] == 0
    assert str(job.id) not in output.getvalue()
    assert str(incident.id) not in output.getvalue()
    assert str(incident.owner.email) not in output.getvalue()
    _claim(str(job.id))
    AIInvestigationJob.objects.filter(pk=job.pk).update(
        lease_until=timezone.now() - timedelta(seconds=1)
    )
    output = StringIO()
    call_command("inspect_ai_jobs", "--json", stdout=output)
    assert json.loads(output.getvalue())["expired_leases"] == 1


@pytest.mark.django_db
def test_successful_completion_has_one_terminal_event(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    job_id = created.json()["job_id"]
    token = _claim(job_id)
    _finish(
        job_id,
        token,
        output=(
            report(entry["event_id"]),
            {"prompt_tokens": 15, "completion_tokens": 9},
            "1.0",
        ),
    )
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "succeeded"
    assert list(job.events.values_list("action", flat=True)) == [
        "submitted",
        "claimed",
        "completed",
    ]
    _finish(job_id, token, failure=RuntimeError("ignored"))
    assert job.events.count() == 3


@pytest.mark.django_db
def test_cancellation_requires_csrf_token(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "configured-provider-token")
    created = create_job(client, incident, snapshot)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(incident.owner)
    denied = csrf_client.post(created["Location"] + "/cancel")
    assert denied.status_code == 403
    assert denied["Cache-Control"] == "private, no-store"
    assert AIInvestigationJob.objects.get(pk=created.json()["job_id"]).state == "queued"
