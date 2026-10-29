import uuid

from django.conf import settings
from django.db import models

from incidents.models import Incident


class EvidenceSnapshot(models.Model):
    """Application-level immutable, locally stored evidence approved for preparation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident, on_delete=models.PROTECT, related_name="evidence_snapshots"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entries = models.JSONField()
    sha256 = models.CharField(max_length=64)
    item_count = models.PositiveSmallIntegerField()
    characters = models.PositiveIntegerField()
    payload_bytes = models.PositiveIntegerField()
    selection_version = models.CharField(max_length=16)
    privacy_policy_version = models.CharField(max_length=16)
    consent_accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["incident", "-created_at"], name="evid_snap_inc_date_idx")]
