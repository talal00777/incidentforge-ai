import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Incident(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        ARCHIVED = "archived", "Archived"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Environment(models.TextChoices):
        PRODUCTION = "production", "Production"
        STAGING = "staging", "Staging"
        DEVELOPMENT = "development", "Development"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incidents"
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidents",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, max_length=4000)
    service_name = models.CharField(max_length=120, blank=True)
    environment = models.CharField(
        max_length=20, choices=Environment.choices, default=Environment.PRODUCTION
    )
    timezone = models.CharField(max_length=64, default="UTC")
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    impact_notes = models.TextField(blank=True, max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("owner", "-created_at"), name="inc_owner_created_idx")]


class IncidentAuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=16, choices=Action.choices)
    changed_fields = models.JSONField(default=list)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at",)


class IncidentTimelineEntry(models.Model):
    class EntryType(models.TextChoices):
        NOTE = "note", "Operator note"
        MILESTONE = "milestone", "Milestone"
        MITIGATION = "mitigation", "Mitigation"
        DECISION = "decision", "Decision"
        HANDOFF = "handoff", "Shift handoff"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name="timeline_entries"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=16, choices=EntryType.choices, default=EntryType.NOTE)
    body = models.TextField(max_length=2000)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [models.Index(fields=("incident", "-occurred_at"), name="inc_timeline_occ_idx")]


class IncidentActionItem(models.Model):
    class Priority(models.TextChoices):
        P0 = "p0", "P0 · Immediate"
        P1 = "p1", "P1 · High"
        P2 = "p2", "P2 · Medium"
        P3 = "p3", "P3 · Follow-up"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="action_items")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    owner_label = models.CharField(max_length=120, blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.P1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("status", "priority", "-created_at")
        indexes = [
            models.Index(fields=("incident", "status", "-created_at"), name="inc_act_status_idx")
        ]


class ReportPurgeReceipt(models.Model):
    incident = models.OneToOneField(
        Incident, on_delete=models.PROTECT, related_name="report_purge_receipt"
    )
    completed_at = models.DateTimeField(auto_now_add=True)
    retention_days = models.PositiveSmallIntegerField()
    postmortems = models.PositiveIntegerField(default=0)
    review_revisions = models.PositiveIntegerField(default=0)
    reviews = models.PositiveIntegerField(default=0)
    reports = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    snapshots = models.PositiveIntegerField(default=0)
