from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from incidents.retention import purge_report_content
from investigations.jobs import _claim, _finish, execute_investigation, reconcile_investigations
from investigations.models import AIInvestigationJob, AIJobExecution, InvestigationReport
from investigations.providers import ProviderFailure
from investigations.tests.test_investigations_m42 import payload, report
from investigations.tests.test_investigations_m42 import record as record


def create_job(client, incident, snapshot, *, key=None, values=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    with patch("investigations.async_views.enqueue_job"):
        return client.post(
            f"/api/v1/incidents/{incident.id}/ai-runs",
            values or payload(snapshot),
            content_type="application/json",
            **headers,
        )


@pytest.mark.django_db
def test_accepted_request_is_persisted_without_calling_provider(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    with patch("investigations.jobs.run_investigation") as run:
        response = create_job(client, incident, snapshot)
        assert response.status_code == 202, response.content
        run.assert_not_called()
        job_id = response.json()["job_id"]
        assert response["Location"].endswith(f"/ai-runs/{job_id}")
        job = AIInvestigationJob.objects.get(pk=job_id)
        assert job.state == "queued"
        run.return_value = (
            report(entry["event_id"]),
            {"prompt_tokens": 23, "completion_tokens": 31},
            "1.0",
        )
        execute_investigation.run(job_id)
        execute_investigation.run(job_id)
    job.refresh_from_db()
    assert job.state == "succeeded"
    assert job.attempt_count == 1
    assert job.attempt.status == "succeeded"
    assert InvestigationReport.objects.filter(attempt=job.attempt).count() == 1
    assert AIJobExecution.objects.filter(job=job, state="succeeded").count() == 1
    assert client.get(response["Location"]).json()["report_id"]
    assert len(client.get(f"/api/v1/incidents/{incident.id}/ai-runs").json()) == 1


@pytest.mark.django_db
def test_idempotency_conflict_and_active_limit(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    first = create_job(client, incident, snapshot, key="run-test-12345")
    again = create_job(client, incident, snapshot, key="run-test-12345")
    assert first.status_code == again.status_code == 202
    assert first.json()["job_id"] == again.json()["job_id"]
    assert AIInvestigationJob.objects.count() == 1
    changed = payload(snapshot)
    changed["temperature"] = 0.7
    assert (
        create_job(client, incident, snapshot, key="run-test-12345", values=changed).status_code
        == 409
    )
    assert create_job(client, incident, snapshot).status_code == 409


@pytest.mark.django_db
def test_cancel_pending_and_owner_isolation(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    response = create_job(client, incident, snapshot)
    path = response["Location"]
    user = get_user_model().objects.create_user(
        f"reviewer-{uuid4()}@example.org", "valid-test-password-527"
    )
    client.force_login(user)
    assert client.get(path).status_code == 404
    assert client.post(path + "/cancel").status_code == 404
    client.force_login(incident.owner)
    canceled = client.post(path + "/cancel")
    assert canceled.status_code == 202
    assert canceled.json()["state"] == "cancelled"
    with patch("investigations.jobs.run_investigation") as call:
        execute_investigation.run(response.json()["job_id"])
        call.assert_not_called()
    assert client.post(path + "/cancel").status_code == 409


@pytest.mark.django_db
def test_transient_failure_retries_with_new_execution(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    job_id = create_job(client, incident, snapshot).json()["job_id"]
    with (
        patch(
            "investigations.jobs.run_investigation",
            side_effect=ProviderFailure("rate_limited", "Busy", 429),
        ),
        patch("investigations.jobs.enqueue_retry") as retry,
    ):
        execute_investigation.run(job_id)
        retry.assert_called_once()
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "retry_wait"
    assert job.attempt_count == 1
    assert job.error_code == "rate_limited"
    AIInvestigationJob.objects.filter(pk=job.pk).update(
        available_at=timezone.now() - timedelta(seconds=1)
    )
    with patch(
        "investigations.jobs.run_investigation",
        return_value=(
            report(entry["event_id"]),
            {"prompt_tokens": 1, "completion_tokens": 1},
            "1.0",
        ),
    ):
        execute_investigation.run(job_id)
    job.refresh_from_db()
    assert job.state == "succeeded"
    assert job.attempt_count == 2
    assert list(job.executions.order_by("number").values_list("state", flat=True)) == [
        "retry_wait",
        "succeeded",
    ]


@pytest.mark.django_db
def test_reconcile_expired_claim_and_fencing(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    job_id = create_job(client, incident, snapshot).json()["job_id"]
    token = _claim(job_id)
    assert token
    AIInvestigationJob.objects.filter(pk=job_id).update(
        lease_until=timezone.now() - timedelta(seconds=1)
    )
    with patch("investigations.jobs.enqueue_job") as send:
        assert reconcile_investigations.run() >= 1
        send.assert_any_call(job_id)
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "retry_wait"
    assert job.executions.get(number=1).state == "interrupted"
    _finish(
        job_id,
        token,
        output=(report(entry["event_id"]), {"prompt_tokens": 1, "completion_tokens": 1}, "1.0"),
    )
    assert not InvestigationReport.objects.filter(attempt=job.attempt).exists()
    with patch(
        "investigations.jobs.run_investigation",
        return_value=(
            report(entry["event_id"]),
            {"prompt_tokens": 1, "completion_tokens": 1},
            "1.0",
        ),
    ):
        execute_investigation.run(job_id)
    job.refresh_from_db()
    assert job.state == "succeeded"
    assert job.attempt_count == 2


@pytest.mark.django_db
def test_running_cancel_discards_provider_result(record, monkeypatch):
    incident, snapshot, entry, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    created = create_job(client, incident, snapshot)
    job_id = created.json()["job_id"]
    token = _claim(job_id)
    assert client.post(created["Location"] + "/cancel").json()["state"] == "cancelling"
    _finish(
        job_id,
        token,
        output=(report(entry["event_id"]), {"prompt_tokens": 1, "completion_tokens": 1}, "1.0"),
    )
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "cancelled"
    assert not InvestigationReport.objects.filter(attempt=job.attempt).exists()


@pytest.mark.django_db
def test_retention_removes_terminal_jobs_before_source_content(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    response = create_job(client, incident, snapshot)
    job = AIInvestigationJob.objects.get(pk=response.json()["job_id"])
    client.post(response["Location"] + "/cancel")
    incident.deleted_at = timezone.now() - timedelta(days=100)
    incident.save(update_fields=["deleted_at"])
    state, _ = purge_report_content(
        incident.pk,
        cutoff=timezone.now() - timedelta(days=90),
        retention_days=90,
        execute=True,
    )
    assert state == "eligible"
    assert not AIInvestigationJob.objects.filter(pk=job.pk).exists()


@pytest.mark.django_db
def test_invalid_consent_and_snapshot_hash_do_not_create_jobs(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    form = payload(snapshot)
    form["transmission_consent"]["accepted"] = False
    assert create_job(client, incident, snapshot, values=form).status_code == 400
    form = payload(snapshot)
    form["transmission_consent"]["snapshot_sha256"] = "0" * 64
    assert create_job(client, incident, snapshot, values=form).status_code == 409
    assert not AIInvestigationJob.objects.exists()


@pytest.mark.django_db
def test_nonretryable_failure_is_terminal(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    job_id = create_job(client, incident, snapshot).json()["job_id"]
    with (
        patch(
            "investigations.jobs.run_investigation",
            side_effect=ProviderFailure("invalid_response", "Invalid JSON", 502),
        ),
        patch("investigations.jobs.enqueue_retry") as retry,
    ):
        execute_investigation.run(job_id)
        retry.assert_not_called()
    job = AIInvestigationJob.objects.get(pk=job_id)
    assert job.state == "failed"
    assert job.attempt_count == 1
    assert job.error_code == "invalid_response"
    assert not InvestigationReport.objects.filter(attempt=job.attempt).exists()


@pytest.mark.django_db
def test_retention_skips_active_investigation(record, monkeypatch):
    incident, snapshot, _, client = record
    monkeypatch.setenv("GROQ_API_KEY", "test-provider-token")
    job_id = create_job(client, incident, snapshot).json()["job_id"]
    incident.deleted_at = timezone.now() - timedelta(days=100)
    incident.save(update_fields=["deleted_at"])
    state, counts = purge_report_content(
        incident.pk,
        cutoff=timezone.now() - timedelta(days=90),
        retention_days=90,
        execute=True,
    )
    assert (state, counts) == ("active", None)
    assert AIInvestigationJob.objects.filter(pk=job_id).exists()


def test_decomposed_generation_checks_cancellation_between_calls():
    from investigations.jobs import ClaimCancelled
    from investigations.service import run_investigation

    entry = {"event_id": str(uuid4()), "message": "gateway timeout", "source_id": str(uuid4())}
    calls = []

    class Adapter:
        def complete(self, **kwargs):
            calls.append(kwargs)
            return {"observed_facts": [], "limitations": []}, {
                "prompt_tokens": 1,
                "completion_tokens": 1,
            }

    def check_cancel():
        if calls:
            raise ClaimCancelled

    with pytest.raises(ClaimCancelled):
        run_investigation(
            provider=object(),
            model="test-model",
            entries=[entry],
            temperature=0.2,
            max_tokens=512,
            prompt_profile="decomposed_verified",
            adapter=Adapter(),
            check_cancel=check_cancel,
        )
    assert len(calls) == 1
