import uuid

from django.conf import settings
from django.db import models

from evidence.models import EvidenceSnapshot
from incidents.models import Incident


class InvestigationAttempt(models.Model):
    """Non-content audit record for each consented external AI attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT)
    snapshot = models.ForeignKey(EvidenceSnapshot, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot_sha256 = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    model_id = models.CharField(max_length=160)
    prompt_profile = models.CharField(max_length=32)
    status = models.CharField(max_length=12, default="started")
    failure_code = models.CharField(max_length=40, blank=True)
    consent_accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class InvestigationReport(models.Model):
    attempt = models.OneToOneField(InvestigationAttempt, on_delete=models.PROTECT)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident, on_delete=models.PROTECT, related_name="investigation_reports"
    )
    snapshot = models.ForeignKey(EvidenceSnapshot, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot_sha256 = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    model_id = models.CharField(max_length=160)
    temperature = models.FloatField()
    max_output_tokens = models.PositiveSmallIntegerField()
    prompt_profile = models.CharField(max_length=32)
    prompt_version = models.CharField(max_length=16)
    response_schema_version = models.CharField(max_length=16)
    report = models.JSONField()
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    consent_accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["incident", "-created_at"], name="inv_report_inc_date_idx")]
