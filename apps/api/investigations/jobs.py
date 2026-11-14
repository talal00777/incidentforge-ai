"""Database-backed investigation execution and recovery."""

import hashlib
import json
import logging
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from investigations.models import (
    AIInvestigationJob,
    AIJobEvent,
    AIJobExecution,
    InvestigationReport,
)
from investigations.providers import ProviderFailure, select_provider
from investigations.service import run_investigation
from investigations.validation import snapshot_entries

logger = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}
ACTIVE = {"queued", "running", "retry_wait", "cancelling"}
RETRYABLE = {"rate_limited", "provider_unreachable", "provider_error"}


class ClaimAbandoned(Exception):
    pass


class ClaimCancelled(Exception):
    pass


def ensure_claim_active(job_id, token):
    current = (
        AIInvestigationJob.objects.filter(pk=job_id)
        .values("claim_token", "state", "cancel_requested", "lease_until")
        .first()
    )
    if (
        current is None
        or current["claim_token"] != token
        or current["lease_until"] is None
        or current["lease_until"] <= timezone.now()
    ):
        raise ClaimAbandoned
    if current["cancel_requested"] or current["state"] == "cancelling":
        raise ClaimCancelled


def request_fingerprint(*, snapshot, fields):
    payload = {
        "snapshot_id": str(snapshot.id),
        "snapshot_sha256": snapshot.sha256,
        "provider": fields["provider"],
        "model_id": fields["model_id"],
        "temperature": fields["temperature"],
        "max_output_tokens": int(fields["max_output_tokens"]),
        "prompt_profile": fields["prompt_profile"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def job_data(job):
    report = InvestigationReport.objects.filter(attempt_id=job.attempt_id).first()
    code = job.error_code or ""
    return {
        "job_id": str(job.id),
        "state": job.state,
        "attempt_count": job.attempt_count,
        "cancel_requested": job.cancel_requested,
        "report_id": str(report.id) if report else None,
        "error": (
            {"code": code, "retryable": job.state == "retry_wait", "message": error_message(code)}
            if code
            else None
        ),
        "available_at": job.available_at,
        "requested_at": job.requested_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def error_message(code):
    if code == "rate_limited":
        return "The provider rate limit was reached."
    if code in ("provider_unreachable", "provider_error"):
        return "The AI provider is unavailable."
    if code == "attempts_exhausted":
        return "The investigation could not be completed after repeated attempts."
    if code == "snapshot_integrity":
        return "The saved evidence could not be verified."
    if code == "incident_deleted":
        return "This incident is no longer available."
    return "The investigation could not be completed."


def enqueue_job(job_id):
    try:
        execute_investigation.delay(str(job_id))
    except Exception:
        # A committed job remains queued for the database reconciler.
        logger.warning("Investigation enqueue failed: job=%s", job_id)


def _lease():
    return timedelta(seconds=settings.AI_JOB_LEASE_SECONDS)


def _event(job, action, *, actor=None, error_code=""):
    AIJobEvent.objects.create(
        job=job,
        actor=actor,
        action=action,
        attempt_number=job.attempt_count,
        error_code=error_code,
    )


def _cancel_locked(job, now):
    job.state = AIInvestigationJob.State.CANCELLED
    job.cancel_requested = True
    job.claim_token = None
    job.lease_until = None
    job.completed_at = now
    job.save(
        update_fields=["state", "cancel_requested", "claim_token", "lease_until", "completed_at"]
    )
    job.attempt.status = "failed"
    job.attempt.failure_code = "cancelled"
    job.attempt.save(update_fields=["status", "failure_code", "updated_at"])
    _event(job, AIJobEvent.Action.CANCELLED)


def cancel_job(job_id, *, actor=None):
    with transaction.atomic():
        job = (
            AIInvestigationJob.objects.select_for_update().select_related("attempt").get(pk=job_id)
        )
        if job.state in TERMINAL:
            return job
        if not job.cancel_requested:
            _event(job, AIJobEvent.Action.CANCEL_REQUESTED, actor=actor)
        job.cancel_requested = True
        if job.state in ("queued", "retry_wait"):
            _cancel_locked(job, timezone.now())
        else:
            job.state = AIInvestigationJob.State.CANCELLING
            job.save(update_fields=["state", "cancel_requested"])
        return job


def _claim(job_id):
    now = timezone.now()
    with transaction.atomic():
        job = (
            AIInvestigationJob.objects.select_for_update().select_related("attempt").get(pk=job_id)
        )
        if job.state not in ("queued", "retry_wait") or job.available_at > now:
            return None
        if job.cancel_requested or job.incident.deleted_at is not None:
            _cancel_locked(job, now)
            return None
        if job.attempt_count >= settings.AI_JOB_MAX_ATTEMPTS:
            job.state = AIInvestigationJob.State.FAILED
            job.error_code = "attempts_exhausted"
            job.completed_at = now
            job.save(update_fields=["state", "error_code", "completed_at"])
            job.attempt.status = "failed"
            job.attempt.failure_code = "attempts_exhausted"
            job.attempt.save(update_fields=["status", "failure_code", "updated_at"])
            _event(job, AIJobEvent.Action.FAILED, error_code="attempts_exhausted")
            return None
        token = uuid4()
        job.state = AIInvestigationJob.State.RUNNING
        job.claim_token = token
        job.lease_until = now + _lease()
        job.attempt_count += 1
        job.started_at = now
        job.error_code = ""
        job.save(
            update_fields=[
                "state",
                "claim_token",
                "lease_until",
                "attempt_count",
                "started_at",
                "error_code",
            ]
        )
        AIJobExecution.objects.create(job=job, number=job.attempt_count, started_at=now)
        _event(job, AIJobEvent.Action.CLAIMED)
        return token


def _finish(job_id, token, *, output=None, failure=None):
    now = timezone.now()
    followup = None
    with transaction.atomic():
        job = (
            AIInvestigationJob.objects.select_for_update()
            .select_related("attempt", "incident", "snapshot")
            .get(pk=job_id)
        )
        if (
            job.claim_token != token
            or job.state not in ("running", "cancelling")
            or job.lease_until is None
            or job.lease_until <= now
        ):
            return None
        execution = AIJobExecution.objects.select_for_update().get(
            job=job, number=job.attempt_count
        )
        if job.cancel_requested or job.incident.deleted_at is not None:
            _cancel_locked(job, now)
            execution.state = "cancelled"
        elif failure is None and output is not None:
            report_body, usage, version = output
            InvestigationReport.objects.get_or_create(
                attempt=job.attempt,
                defaults={
                    "incident": job.incident,
                    "snapshot": job.snapshot,
                    "created_by": job.owner,
                    "snapshot_sha256": job.snapshot.sha256,
                    "provider": job.provider,
                    "model_id": job.model_id,
                    "temperature": job.temperature,
                    "max_output_tokens": job.max_output_tokens,
                    "prompt_profile": job.prompt_profile,
                    "prompt_version": version,
                    "response_schema_version": report_body["schema_version"],
                    "report": report_body,
                    "input_tokens": usage["prompt_tokens"] or None,
                    "output_tokens": usage["completion_tokens"] or None,
                    "consent_accepted_at": job.attempt.consent_accepted_at,
                },
            )
            job.state = AIInvestigationJob.State.SUCCEEDED
            job.error_code = ""
            job.completed_at = now
            job.attempt.status = "succeeded"
            job.attempt.failure_code = ""
            execution.state = "succeeded"
        else:
            code = failure.code if isinstance(failure, ProviderFailure) else "execution_failed"
            job.error_code = code
            if code in RETRYABLE and job.attempt_count < settings.AI_JOB_MAX_ATTEMPTS:
                job.state = AIInvestigationJob.State.RETRY_WAIT
                delay = min(300, 5 * 2 ** (job.attempt_count - 1) + (job.id.int % 7))
                job.available_at = now + timedelta(seconds=delay)
                followup = delay
                execution.state = "retry_wait"
            else:
                job.state = AIInvestigationJob.State.FAILED
                job.completed_at = now
                job.attempt.status = "failed"
                job.attempt.failure_code = code
                execution.state = "failed"
            execution.error_code = code
        job.claim_token = None
        job.lease_until = None
        job.save()
        job.attempt.save(update_fields=["status", "failure_code", "updated_at"])
        execution.completed_at = now
        execution.save(update_fields=["state", "error_code", "completed_at"])
        if job.state == AIInvestigationJob.State.SUCCEEDED:
            _event(job, AIJobEvent.Action.COMPLETED)
        elif job.state == AIInvestigationJob.State.FAILED:
            _event(job, AIJobEvent.Action.FAILED, error_code=job.error_code)
        elif job.state == AIInvestigationJob.State.RETRY_WAIT:
            _event(job, AIJobEvent.Action.RETRY_SCHEDULED, error_code=job.error_code)
    return followup


def enqueue_retry(job_id, delay):
    try:
        execute_investigation.apply_async(args=[str(job_id)], countdown=delay)
    except Exception:
        logger.warning("Investigation retry enqueue failed: job=%s", job_id)


@shared_task(acks_late=True, reject_on_worker_lost=True)
def execute_investigation(job_id):
    try:
        token = _claim(job_id)
        if token is None:
            return
        job = AIInvestigationJob.objects.select_related("snapshot").get(pk=job_id)
        try:
            entries = snapshot_entries(job.snapshot)
            profile = select_provider(job.provider, job.model_id)
            output = run_investigation(
                provider=profile,
                model=job.model_id,
                entries=entries,
                temperature=job.temperature,
                max_tokens=job.max_output_tokens,
                prompt_profile=job.prompt_profile,
                check_cancel=lambda: ensure_claim_active(job_id, token),
            )
        except ClaimAbandoned:
            return
        except ClaimCancelled:
            _finish(job_id, token, failure=ProviderFailure("cancelled", "Cancelled", 409))
            return
        except ProviderFailure as exc:
            delay = _finish(job_id, token, failure=exc)
        except Exception:
            logger.exception("Investigation execution failed: job=%s", job_id)
            delay = _finish(job_id, token, failure=RuntimeError("execution_failed"))
        else:
            delay = _finish(job_id, token, output=output)
        if delay is not None:
            enqueue_retry(job_id, delay)
    except AIInvestigationJob.DoesNotExist:
        return


@shared_task
def reconcile_investigations():
    now = timezone.now()
    pending = []
    with transaction.atomic():
        due = Q(state__in=["queued", "retry_wait"], available_at__lte=now)
        expired = Q(state__in=["running", "cancelling"]) & (
            Q(lease_until__lte=now) | Q(lease_until__isnull=True)
        )
        jobs = list(
            AIInvestigationJob.objects.select_for_update(skip_locked=True)
            .filter(due | expired)
            .order_by("requested_at")[: settings.AI_JOB_RECONCILE_BATCH_SIZE]
        )
        for job in jobs:
            if job.state in ("running", "cancelling"):
                if job.lease_until is not None and job.lease_until > now:
                    continue
                execution = AIJobExecution.objects.filter(job=job, number=job.attempt_count).first()
                if execution:
                    execution.state = "interrupted"
                    execution.error_code = "lease_expired"
                    execution.completed_at = now
                    execution.save(update_fields=["state", "error_code", "completed_at"])
                _event(job, AIJobEvent.Action.INTERRUPTED, error_code="lease_expired")
                if job.cancel_requested:
                    _cancel_locked(job, now)
                    continue
                job.claim_token = None
                job.lease_until = None
                if job.attempt_count >= settings.AI_JOB_MAX_ATTEMPTS:
                    job.state = AIInvestigationJob.State.FAILED
                    job.error_code = "attempts_exhausted"
                    job.completed_at = now
                    job.attempt.status = "failed"
                    job.attempt.failure_code = "attempts_exhausted"
                    job.attempt.save(update_fields=["status", "failure_code", "updated_at"])
                    _event(job, AIJobEvent.Action.FAILED, error_code="attempts_exhausted")
                else:
                    job.state = AIInvestigationJob.State.RETRY_WAIT
                    job.available_at = now
                    _event(job, AIJobEvent.Action.RETRY_SCHEDULED, error_code="lease_expired")
                job.save()
            if job.state in ("queued", "retry_wait") and job.available_at <= now:
                pending.append(str(job.id))
    for job_id in pending:
        enqueue_job(job_id)
    return len(pending)
