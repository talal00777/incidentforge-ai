import hashlib
from collections import Counter

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.parser import parse_line
from ingestion.storage import path_for


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def process_ingestion(self, job_id):
    with transaction.atomic():
        job = IngestionJob.objects.select_for_update().get(id=job_id)
        if job.state == IngestionJob.State.SUCCEEDED:
            return
        if job.state == IngestionJob.State.RUNNING:
            return
        job.state = IngestionJob.State.RUNNING
        job.attempts += 1
        job.started_at = timezone.now()
        job.save(update_fields=["state", "attempts", "started_at"])
    try:
        remaining = max(0, settings.INGESTION_MAX_EVENTS_PER_INCIDENT - LogEvent.objects.filter(incident_id=job.incident_id).count())
        total_accepted = 0
        total_rejected = 0
        for source in job.sources.all().order_by("created_at"):
            accepted = 0
            rejected = 0
            warnings = Counter()
            batch = []
            source_path = path_for(source.object_key)
            digest = hashlib.sha256()
            with source_path.open("rb") as verification_stream:
                for chunk in iter(lambda: verification_stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != source.sha256:
                raise ValueError("source_integrity_mismatch")
            with source_path.open("rb") as handle:
                for line_number, line in enumerate(handle, 1):
                    event, warning = parse_line(line, line_number)
                    if warning:
                        rejected += 1
                        warnings[warning] += 1
                        continue
                    if accepted >= remaining:
                        rejected += 1
                        warnings["incident_event_limit"] += 1
                        continue
                    batch.append(LogEvent(incident_id=job.incident_id, source=source, observed_at=timezone.now(), **event))
                    accepted += 1
                    if len(batch) == 500:
                        LogEvent.objects.bulk_create(batch, ignore_conflicts=True)
                        batch.clear()
            if batch:
                LogEvent.objects.bulk_create(batch, ignore_conflicts=True)
            source.state = LogSource.State.COMPLETE
            source.accepted = LogEvent.objects.filter(source=source).count()
            source.rejected = rejected
            source.warnings = [{"code": code, "count": count} for code, count in sorted(warnings.items())]
            source.save(update_fields=["state", "accepted", "rejected", "warnings"])
            remaining -= source.accepted
            total_accepted += source.accepted
            total_rejected += rejected
        job.state = IngestionJob.State.SUCCEEDED
        job.accepted = total_accepted
        job.rejected = total_rejected
        job.error_code = ""
    except Exception:
        job.state = IngestionJob.State.FAILED
        job.error_code = "INGESTION_PROCESSING_FAILED"
        for source in job.sources.filter(state=LogSource.State.QUEUED):
            source.state = LogSource.State.FAILED
            source.save(update_fields=["state"])
        raise
    finally:
        job.completed_at = timezone.now()
        job.save(update_fields=["state", "accepted", "rejected", "error_code", "completed_at"])
