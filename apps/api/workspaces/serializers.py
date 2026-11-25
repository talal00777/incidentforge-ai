import re

from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers

from workspaces.models import AlertWebhook, WebhookDelivery, Workspace, WorkspaceMembership
from workspaces.webhooks import UnsafeWebhookTarget, mask_signing_secret, validate_webhook_url

User = get_user_model()
SLUG_CLEAN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


class WorkspaceCreateUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120)
    slug = serializers.CharField(required=False, allow_blank=True, max_length=80)
    description = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Workspace name must be at least 2 characters.")
        return cleaned

    def validate_slug(self, value: str) -> str:
        cleaned = slugify(value.strip())
        if value.strip() and not SLUG_CLEAN_RE.match(cleaned):
            raise serializers.ValidationError(
                "Slug must be 3-80 lowercase letters, digits, or hyphens."
            )
        return cleaned


class WorkspaceSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    my_role = serializers.ChoiceField(choices=WorkspaceMembership.Role.choices)
    member_count = serializers.IntegerField()
    incident_count = serializers.IntegerField()
    webhook_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class WorkspaceMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    user_id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    role = serializers.ChoiceField(choices=WorkspaceMembership.Role.choices)
    created_at = serializers.DateTimeField()


class WorkspaceMemberAddSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=WorkspaceMembership.Role.choices, default=WorkspaceMembership.Role.RESPONDER
    )

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if not User.objects.filter(email__iexact=normalized, is_active=True).exists():
            raise serializers.ValidationError("No active account found with that email address.")
        return normalized


class WorkspaceMemberRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=WorkspaceMembership.Role.choices)


class AlertWebhookCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120)
    provider = serializers.ChoiceField(
        choices=AlertWebhook.Provider.choices, default=AlertWebhook.Provider.GENERIC
    )
    target_url = serializers.URLField(max_length=500)
    event_types = serializers.ListField(
        child=serializers.ChoiceField(choices=list(AlertWebhook.SUPPORTED_EVENTS)),
        allow_empty=False,
        default=lambda: ["incident.created", "incident.status_changed", "postmortem.finalized"],
    )
    min_severity = serializers.ChoiceField(
        choices=AlertWebhook.MinSeverity.choices, default=AlertWebhook.MinSeverity.LOW
    )
    is_active = serializers.BooleanField(default=True)

    def validate_target_url(self, value: str) -> str:
        try:
            return validate_webhook_url(value, resolve_dns=False)
        except UnsafeWebhookTarget as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_event_types(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AlertWebhookUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120, required=False)
    provider = serializers.ChoiceField(choices=AlertWebhook.Provider.choices, required=False)
    target_url = serializers.URLField(max_length=500, required=False)
    event_types = serializers.ListField(
        child=serializers.ChoiceField(choices=list(AlertWebhook.SUPPORTED_EVENTS)),
        allow_empty=False,
        required=False,
    )
    min_severity = serializers.ChoiceField(choices=AlertWebhook.MinSeverity.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_target_url(self, value: str) -> str:
        try:
            return validate_webhook_url(value, resolve_dns=False)
        except UnsafeWebhookTarget as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_event_types(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class WebhookDeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_type = serializers.CharField()
    incident_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=WebhookDelivery.Status.choices)
    http_status = serializers.IntegerField(allow_null=True)
    latency_ms = serializers.IntegerField(allow_null=True)
    request_payload = serializers.JSONField()
    response_excerpt = serializers.CharField(allow_blank=True)
    error_message = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class AlertWebhookResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    provider = serializers.ChoiceField(choices=AlertWebhook.Provider.choices)
    target_url = serializers.URLField()
    signing_secret_preview = serializers.CharField()
    signing_secret = serializers.CharField(required=False)
    event_types = serializers.ListField(child=serializers.CharField())
    min_severity = serializers.ChoiceField(choices=AlertWebhook.MinSeverity.choices)
    is_active = serializers.BooleanField()
    delivery_count = serializers.IntegerField()
    last_delivery_status = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class WebhookTestRequestSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(default=True)


def serialize_workspace(workspace: Workspace, role: str, counts: dict) -> dict:
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "my_role": role,
        "member_count": counts.get("member_count", 0),
        "incident_count": counts.get("incident_count", 0),
        "webhook_count": counts.get("webhook_count", 0),
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }


def serialize_webhook(webhook: AlertWebhook, *, reveal_secret: bool = False) -> dict:
    last = webhook.deliveries.order_by("-created_at").values_list("status", flat=True).first()
    data = {
        "id": str(webhook.id),
        "name": webhook.name,
        "provider": webhook.provider,
        "target_url": webhook.target_url,
        "signing_secret_preview": mask_signing_secret(webhook.signing_secret),
        "event_types": list(webhook.event_types),
        "min_severity": webhook.min_severity,
        "is_active": webhook.is_active,
        "delivery_count": webhook.deliveries.count(),
        "last_delivery_status": last or "",
        "created_at": webhook.created_at,
        "updated_at": webhook.updated_at,
    }
    if reveal_secret:
        data["signing_secret"] = webhook.signing_secret
    return data


def serialize_delivery(item: WebhookDelivery) -> dict:
    return {
        "id": str(item.id),
        "event_type": item.event_type,
        "incident_id": str(item.incident_id) if item.incident_id else None,
        "status": item.status,
        "http_status": item.http_status,
        "latency_ms": item.latency_ms,
        "request_payload": item.request_payload,
        "response_excerpt": item.response_excerpt,
        "error_message": item.error_message,
        "created_at": item.created_at,
    }
