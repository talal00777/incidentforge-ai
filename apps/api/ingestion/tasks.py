import hashlib
import logging
from collections import Counter
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.db import OperationalError, transaction
from django.db.models import Q
from django.utils import timezone

from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.parser import VERSION, iter_records
from ingestion.storage import path_for

logger = logging.getLogger(__name__)
BATCH_SIZE = 500
MAX_ATTEMPTS = 3


class ClaimLost(Exception):
    """The job lease is no longer held by this execution."""


def _lease_duration():
    return timedelta(seconds=settings.INGESTION_LEASE_SECONDS)


def _claim_job(job_id):
    now = timezone.now()
    with transaction.atomic():
        job = IngestionJob.objects.select_for_update().get(pk=job_id)
        if job.state in (IngestionJob.State.SUCCEEDED, IngestionJob.State.FAILED):
            return None
        if job.state == IngestionJob.State.RUNNING and job.lease_until and job.lease_until > now:
            return None
        if job.attempts >= MAX_ATTEMPTS:
            job.state = IngestionJob.State.FAILED
            job.error_code = "INGESTION_ATTEMPTS_EXHAUSTED"
            job.completed_at = now
            job.lease_until = None
            job.claim_token = None
            job.save(
                update_fields=["state", "error_code", "completed_at", "lease_until", "claim_token"]
            )
            job.sources.filter(state=LogSource.State.QUEUED).update(state=LogSource.State.FAILED)
            return None
        token = uuid4()
        job.state = IngestionJob.State.RUNNING
        job.attempts += 1
        job.started_at = now
        job.completed_at = None
        job.claim_token = token
        job.lease_until = now + _lease_duration()
        job.error_code = ""
        job.save(
            update_fields=[
                "state",
                "attempts",
                "started_at",
                "completed_at",
                "claim_token",
                "lease_until",
                "error_code",
            ]
        )
        return token


def _owned_job(job_id, token):
    job = IngestionJob.objects.select_for_update().get(pk=job_id)
    if (
        job.state != IngestionJob.State.RUNNING
        or job.claim_token != token
        or job.lease_until is None
        or job.lease_until <= timezone.now()
    ):
        raise ClaimLost
    return job


def _heartbeat(job_id, token, events=()):
    with transaction.atomic():
        job = _owned_job(job_id, token)
        if events:
            LogEvent.objects.bulk_create(events, ignore_conflicts=True, batch_size=BATCH_SIZE)
        job.lease_until = timezone.now() + _lease_duration()
        job.save(update_fields=["lease_until"])


def _verify_source(job_id, token, source):
    digest = hashlib.sha256()
    with path_for(source.object_key).open("rb") as handle:
        for index, chunk in enumerate(iter(lambda: handle.read(1024 * 1024), b""), 1):
            digest.update(chunk)
            if index % 4 == 0:
                _heartbeat(job_id, token)
    if digest.hexdigest() != source.sha256:
        raise ValueError("source_integrity_mismatch")


def _process_source(job_id, token, source, incident_id):
    if source.state == LogSource.State.COMPLETE:
        return
    _verify_source(job_id, token, source)
    if source.parser_version != VERSION:
        with transaction.atomic():
            _owned_job(job_id, token)
            locked = LogSource.objects.select_for_update().get(pk=source.pk)
            if locked.state == LogSource.State.COMPLETE:
                return
            LogEvent.objects.filter(source=locked).exclude(parser_version=VERSION).delete()
            locked.parser_version = VERSION
            locked.save(update_fields=["parser_version"])
        source.parser_version = VERSION
    other_count = LogEvent.objects.filter(incident_id=incident_id).exclude(source=source).count()
    capacity = max(0, settings.INGESTION_MAX_EVENTS_PER_INCIDENT - other_count)
    accepted_in_stream = 0
    rejected = 0
    warnings = Counter()
    batch = []
    with path_for(source.object_key).open("rb") as handle:
        for record_number, (event, warning) in enumerate(iter_records(handle), 1):
            if warning:
                rejected += 1
                warnings[warning] += 1
            elif accepted_in_stream >= capacity:
                rejected += 1
                warnings["incident_event_limit"] += 1
            else:
                accepted_in_stream += 1
                quality = event["timestamp_quality"]
                if quality != "explicit":
                    warnings[f"timestamp_{quality}"] += 1
                batch.append(
                    LogEvent(
                        incident_id=incident_id,
                        source=source,
                        observed_at=timezone.now(),
                        **event,
                    )
                )
            if record_number % BATCH_SIZE == 0:
                _heartbeat(job_id, token, batch)
                batch.clear()
    _heartbeat(job_id, token, batch)
    with transaction.atomic():
        _owned_job(job_id, token)
        source = LogSource.objects.select_for_update().get(pk=source.pk)
        source.accepted = LogEvent.objects.filter(source=source).count()
        source.rejected = rejected
        source.warnings = [
            {"code": code, "count": count} for code, count in sorted(warnings.items())
        ]
        source.state = LogSource.State.COMPLETE
        source.save(update_fields=["accepted", "rejected", "warnings", "state"])


def _mark_failure(job_id, token, code, *, retry=False):
    with transaction.atomic():
        job = IngestionJob.objects.select_for_update().get(pk=job_id)
        if job.claim_token != token or job.state != IngestionJob.State.RUNNING:
            return False
        job.state = IngestionJob.State.QUEUED if retry else IngestionJob.State.FAILED
        job.error_code = code
        job.claim_token = None
        job.lease_until = None
        job.completed_at = None if retry else timezone.now()
        job.save(
            update_fields=["state", "error_code", "claim_token", "lease_until", "completed_at"]
        )
        if not retry:
            job.sources.filter(state=LogSource.State.QUEUED).update(state=LogSource.State.FAILED)
        return True


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2)
def process_ingestion(self, job_id):
    token = _claim_job(job_id)
    if token is None:
        return
    try:
        job = IngestionJob.objects.get(pk=job_id)
        for source in job.sources.order_by("created_at", "id"):
            _process_source(job_id, token, source, job.incident_id)
        with transaction.atomic():
            job = _owned_job(job_id, token)
            sources = job.sources.all()
            job.accepted = sum(source.accepted for source in sources)
            job.rejected = sum(source.rejected for source in sources)
            job.state = IngestionJob.State.SUCCEEDED
            job.error_code = ""
            job.completed_at = timezone.now()
            job.lease_until = None
            job.claim_token = None
            job.save(
                update_fields=[
                    "state",
                    "accepted",
                    "rejected",
                    "error_code",
                    "completed_at",
                    "lease_until",
                    "claim_token",
                ]
            )
    except ClaimLost:
        return
    except OperationalError as exc:
        if _mark_failure(
            job_id,
            token,
            "INGESTION_TRANSIENT_FAILURE",
            retry=IngestionJob.objects.get(pk=job_id).attempts < MAX_ATTEMPTS,
        ):
            job = IngestionJob.objects.get(pk=job_id)
            if job.state == IngestionJob.State.QUEUED:
                raise self.retry(countdown=min(60, 2**job.attempts)) from exc
        return
    except ValueError as exc:
        code = (
            "INGESTION_SOURCE_INTEGRITY_FAILED"
            if str(exc) == "source_integrity_mismatch"
            else "INGESTION_PROCESSING_FAILED"
        )
        _mark_failure(job_id, token, code)
    except OSError:
        _mark_failure(job_id, token, "INGESTION_SOURCE_UNAVAILABLE")
    except Exception:
        logger.error("Ingestion job %s failed during processing", job_id)
        _mark_failure(job_id, token, "INGESTION_PROCESSING_FAILED")


@shared_task
def reconcile_ingestion():
    now = timezone.now()
    queued_cutoff = now - timedelta(seconds=30)
    jobs = (
        IngestionJob.objects.filter(
            Q(state=IngestionJob.State.QUEUED, requested_at__lt=queued_cutoff)
            | Q(state=IngestionJob.State.RUNNING, lease_until__lt=now)
            | Q(state=IngestionJob.State.RUNNING, lease_until__isnull=True)
        )
        .order_by("requested_at")
        .values_list("id", flat=True)[:100]
    )
    dispatched = 0
    for job_id in jobs:
        try:
            process_ingestion.delay(str(job_id))
            dispatched += 1
        except Exception:
            logger.warning("Unable to enqueue ingestion job %s", job_id)
    return dispatched
