from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from incidents.models import Incident
from workspaces.models import Workspace
from workspaces.permissions import user_role_for_incident


class IncidentSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    workspace_name = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = (
            "id",
            "title",
            "description",
            "service_name",
            "environment",
            "timezone",
            "severity",
            "status",
            "impact_notes",
            "workspace_id",
            "workspace_name",
            "user_role",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "workspace_name", "user_role", "created_at", "updated_at")

    def get_workspace_name(self, obj: Incident) -> str:
        if obj.workspace_id and obj.workspace:
            return obj.workspace.name
        return ""

    def get_user_role(self, obj: Incident) -> str:
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return "owner"
        return user_role_for_incident(request.user, obj) or "viewer"

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Title must contain at least three characters")
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Enter a valid IANA timezone") from None
        return value

    def validate_workspace_id(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required to assign a workspace.")
        exists = Workspace.objects.filter(
            pk=value,
            memberships__user=request.user,
            memberships__role__in=("owner", "responder"),
        ).exists()
        if not exists:
            raise serializers.ValidationError(
                "Choose a workspace where you hold owner or responder permissions."
            )
        return value
