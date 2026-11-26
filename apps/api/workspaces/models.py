import secrets
import uuid

from django.conf import settings
from django.db import models


def generate_webhook_secret() -> str:
    return f"whsec_{secrets.token_hex(24)}"


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_workspaces"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")


class WorkspaceMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        RESPONDER = "responder", "Responder"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.RESPONDER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "user"),
                name="ws_member_unique_workspace_user",
            )
        ]


class AlertWebhook(models.Model):
    class Provider(models.TextChoices):
        GENERIC = "generic", "Generic JSON"
        SLACK = "slack", "Slack"
        DISCORD = "discord", "Discord"
        PAGERDUTY = "pagerduty", "PagerDuty"

    class MinSeverity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    SUPPORTED_EVENTS = (
        "incident.created",
        "incident.status_changed",
        "postmortem.finalized",
        "webhook.test",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="webhooks")
    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.GENERIC)
    target_url = models.URLField(max_length=500)
    signing_secret = models.CharField(max_length=128, default=generate_webhook_secret)
    event_types = models.JSONField(default=list)
    min_severity = models.CharField(
        max_length=12, choices=MinSeverity.choices, default=MinSeverity.LOW
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_webhooks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"
        DRY_RUN = "dry_run", "Dry-run preview"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook = models.ForeignKey(AlertWebhook, on_delete=models.CASCADE, related_name="deliveries")
    event_type = models.CharField(max_length=48)
    incident_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    request_payload = models.JSONField(default=dict)
    response_excerpt = models.CharField(max_length=400, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("webhook", "-created_at"), name="ws_wh_delivery_created_idx")
        ]
