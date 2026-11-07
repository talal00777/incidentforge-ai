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


class InvestigationReview(models.Model):
    """Mutable pointer to append-only human review revisions of one AI report."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.OneToOneField(
        InvestigationReport, on_delete=models.PROTECT, related_name="human_review"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    latest_revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class InvestigationReviewRevision(models.Model):
    """Historical reviewer input; generated investigation data is never overwritten."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        InvestigationReview, on_delete=models.PROTECT, related_name="revisions"
    )
    number = models.PositiveIntegerField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=[("draft", "Draft"), ("reviewed", "Reviewed")])
    impact_notes = models.TextField(blank=True)
    remediation_notes = models.TextField(blank=True)
    hypotheses = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-number",)
        constraints = [
            models.UniqueConstraint(fields=["review", "number"], name="inv_review_revision_unique")
        ]


class PostmortemVersion(models.Model):
    """Immutable, versioned capture of AI findings and a specific human review."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident, on_delete=models.PROTECT, related_name="postmortem_versions"
    )
    investigation = models.ForeignKey(
        InvestigationReport, on_delete=models.PROTECT, related_name="postmortem_versions"
    )
    review_revision = models.ForeignKey(
        InvestigationReviewRevision, on_delete=models.PROTECT, related_name="postmortem_versions"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    schema_version = models.CharField(max_length=12, default="1.0")
    content = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version",)
        indexes = [models.Index(fields=["incident", "-version"], name="inv_pm_inc_ver_idx")]
        constraints = [
            models.UniqueConstraint(fields=["incident", "version"], name="inv_pm_inc_version_uniq"),
            models.UniqueConstraint(
                fields=["investigation", "review_revision"], name="inv_pm_report_review_uniq"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Postmortem versions are immutable; create a new version.")
        super().save(*args, **kwargs)
