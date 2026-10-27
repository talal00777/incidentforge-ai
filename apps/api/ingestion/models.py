import uuid

from django.conf import settings
from django.db import models

from incidents.models import Incident


class IngestionJob(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="ingestion_jobs")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    state = models.CharField(max_length=12, choices=State.choices, default=State.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    accepted = models.PositiveIntegerField(default=0)
    rejected = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["incident", "-requested_at"], name="ing_job_inc_date_idx")]


class LogSource(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="log_sources")
    job = models.ForeignKey(IngestionJob, on_delete=models.PROTECT, related_name="sources")
    filename = models.CharField(max_length=255)
    object_key = models.CharField(max_length=150, unique=True)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    parser_version = models.CharField(max_length=32, default="m2.1")
    state = models.CharField(max_length=12, choices=State.choices, default=State.QUEUED)
    accepted = models.PositiveIntegerField(default=0)
    rejected = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["incident", "created_at"], name="ing_src_inc_date_idx")]


class LogEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="log_events")
    source = models.ForeignKey(LogSource, on_delete=models.PROTECT, related_name="events")
    line_start = models.PositiveIntegerField()
    line_end = models.PositiveIntegerField()
    occurred_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField()
    timestamp_quality = models.CharField(max_length=32)
    severity = models.CharField(max_length=16, blank=True)
    service = models.CharField(max_length=120, blank=True)
    trace_id = models.CharField(max_length=128, blank=True)
    redacted_message = models.TextField(max_length=4096)
    fingerprint = models.CharField(max_length=64)
    parser_version = models.CharField(max_length=32, default="m2.1")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "line_start", "line_end", "parser_version"],
                name="ing_event_idempotence",
            )
        ]
        indexes = [
            models.Index(fields=["incident", "occurred_at"], name="ing_evt_time_idx"),
            models.Index(
                fields=["incident", "severity", "occurred_at"], name="ing_evt_severity_idx"
            ),
        ]
