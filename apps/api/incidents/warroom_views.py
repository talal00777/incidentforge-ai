from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from evidence.models import EvidenceSnapshot
from incidents.models import IncidentActionItem, IncidentAuditEvent, IncidentTimelineEntry
from ingestion.models import LogSource
from investigations.models import InvestigationReport, PostmortemVersion
from workspaces.permissions import get_accessible_incident_or_404


class TimelineEntryCreateSerializer(serializers.Serializer):
    entry_type = serializers.ChoiceField(
        choices=IncidentTimelineEntry.EntryType.choices,
        default=IncidentTimelineEntry.EntryType.NOTE,
    )
    body = serializers.CharField(min_length=2, max_length=2000)
    occurred_at = serializers.DateTimeField(required=False)

    def validate_body(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Timeline note must contain at least 2 characters.")
        return cleaned


class UnifiedTimelineItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    source_kind = serializers.ChoiceField(
        choices=("operator", "audit", "source", "snapshot", "ai", "postmortem")
    )
    entry_type = serializers.CharField()
    body = serializers.CharField()
    actor_label = serializers.CharField(allow_blank=True)
    occurred_at = serializers.DateTimeField()
    deletable = serializers.BooleanField()


class ActionItemCreateSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=2, max_length=200)
    owner_label = serializers.CharField(required=False, allow_blank=True, max_length=120)
    priority = serializers.ChoiceField(
        choices=IncidentActionItem.Priority.choices,
        default=IncidentActionItem.Priority.P1,
    )
    status = serializers.ChoiceField(
        choices=IncidentActionItem.Status.choices,
        default=IncidentActionItem.Status.OPEN,
    )
    due_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Action item title must be at least 2 characters.")
        return cleaned


class ActionItemUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=2, max_length=200, required=False)
    owner_label = serializers.CharField(allow_blank=True, max_length=120, required=False)
    priority = serializers.ChoiceField(choices=IncidentActionItem.Priority.choices, required=False)
    status = serializers.ChoiceField(choices=IncidentActionItem.Status.choices, required=False)
    due_at = serializers.DateTimeField(allow_null=True, required=False)


class ActionItemResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    owner_label = serializers.CharField(allow_blank=True)
    priority = serializers.ChoiceField(choices=IncidentActionItem.Priority.choices)
    status = serializers.ChoiceField(choices=IncidentActionItem.Status.choices)
    due_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    created_by_email = serializers.EmailField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


def _serialize_action_item(item: IncidentActionItem) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "owner_label": item.owner_label,
        "priority": item.priority,
        "status": item.status,
        "due_at": item.due_at,
        "completed_at": item.completed_at,
        "created_by_email": item.created_by.email,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _build_unified_timeline(incident) -> list[dict]:
    items: list[dict] = []

    for entry in (
        IncidentTimelineEntry.objects.filter(incident=incident)
        .select_related("author")
        .order_by("-occurred_at")[:80]
    ):
        items.append(
            {
                "id": str(entry.id),
                "source_kind": "operator",
                "entry_type": entry.entry_type,
                "body": entry.body,
                "actor_label": entry.author.email,
                "occurred_at": entry.occurred_at,
                "deletable": True,
            }
        )

    for audit in (
        IncidentAuditEvent.objects.filter(incident=incident)
        .select_related("actor")
        .order_by("-occurred_at")[:30]
    ):
        fields_note = f" ({', '.join(audit.changed_fields)})" if audit.changed_fields else ""
        items.append(
            {
                "id": f"audit:{audit.id}",
                "source_kind": "audit",
                "entry_type": audit.action,
                "body": f"Incident {audit.action}{fields_note}.",
                "actor_label": audit.actor.email,
                "occurred_at": audit.occurred_at,
                "deletable": False,
            }
        )

    for src in LogSource.objects.filter(incident=incident).order_by("-created_at")[:25]:
        items.append(
            {
                "id": f"source:{src.id}",
                "source_kind": "source",
                "entry_type": "log_upload",
                "body": f"Ingested {src.filename} ({src.accepted} accepted, {src.rejected} rejected).",
                "actor_label": "ingestion",
                "occurred_at": src.created_at,
                "deletable": False,
            }
        )

    for snap in (
        EvidenceSnapshot.objects.filter(incident=incident)
        .select_related("created_by")
        .order_by("-created_at")[:15]
    ):
        items.append(
            {
                "id": f"snapshot:{snap.id}",
                "source_kind": "snapshot",
                "entry_type": "evidence_frozen",
                "body": f"Froze redacted evidence snapshot ({snap.item_count} events, SHA-256 {snap.sha256[:10]}…).",
                "actor_label": snap.created_by.email,
                "occurred_at": snap.created_at,
                "deletable": False,
            }
        )

    for report in (
        InvestigationReport.objects.filter(incident=incident)
        .select_related("created_by")
        .order_by("-created_at")[:15]
    ):
        items.append(
            {
                "id": f"ai:{report.id}",
                "source_kind": "ai",
                "entry_type": "ai_report",
                "body": f"Generated AI investigation ({report.provider}/{report.model_id}, {report.prompt_profile}).",
                "actor_label": report.created_by.email,
                "occurred_at": report.created_at,
                "deletable": False,
            }
        )

    for pm in (
        PostmortemVersion.objects.filter(incident=incident)
        .select_related("created_by")
        .order_by("-created_at")[:15]
    ):
        items.append(
            {
                "id": f"postmortem:{pm.id}",
                "source_kind": "postmortem",
                "entry_type": "postmortem_version",
                "body": f"Finalized immutable postmortem v{pm.version} (review rev {pm.review_revision_number}).",
                "actor_label": pm.created_by.email,
                "occurred_at": pm.created_at,
                "deletable": False,
            }
        )

    items.sort(key=lambda row: row["occurred_at"], reverse=True)
    return items[:120]


class IncidentTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["incidents"],
        request=None,
        responses={200: UnifiedTimelineItemSerializer(many=True)},
    )
    def get(self, request, incident_id):
        incident = get_accessible_incident_or_404(request.user, incident_id)
        return Response(_build_unified_timeline(incident))

    @extend_schema(
        tags=["incidents"],
        request=TimelineEntryCreateSerializer,
        responses={201: UnifiedTimelineItemSerializer},
    )
    def post(self, request, incident_id):
        incident = get_accessible_incident_or_404(request.user, incident_id, require_write=True)
        serializer = TimelineEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entry = IncidentTimelineEntry.objects.create(
            incident=incident,
            author=request.user,
            entry_type=data["entry_type"],
            body=data["body"],
            occurred_at=data.get("occurred_at") or timezone.now(),
        )
        return Response(
            {
                "id": str(entry.id),
                "source_kind": "operator",
                "entry_type": entry.entry_type,
                "body": entry.body,
                "actor_label": request.user.email,
                "occurred_at": entry.occurred_at,
                "deletable": True,
            },
            status=status.HTTP_201_CREATED,
        )


class IncidentTimelineDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["incidents"], request=None, responses={204: None})
    def delete(self, request, incident_id, entry_id):
        incident = get_accessible_incident_or_404(request.user, incident_id, require_write=True)
        entry = get_object_or_404(IncidentTimelineEntry, pk=entry_id, incident=incident)
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentActionItemsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["incidents"],
        request=None,
        responses={200: ActionItemResponseSerializer(many=True)},
    )
    def get(self, request, incident_id):
        incident = get_accessible_incident_or_404(request.user, incident_id)
        rows = (
            IncidentActionItem.objects.filter(incident=incident)
            .select_related("created_by")
            .order_by("status", "priority", "-created_at")
        )
        return Response([_serialize_action_item(item) for item in rows])

    @extend_schema(
        tags=["incidents"],
        request=ActionItemCreateSerializer,
        responses={201: ActionItemResponseSerializer},
    )
    def post(self, request, incident_id):
        incident = get_accessible_incident_or_404(request.user, incident_id, require_write=True)
        serializer = ActionItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        completed_at = timezone.now() if data["status"] == IncidentActionItem.Status.DONE else None
        item = IncidentActionItem.objects.create(
            incident=incident,
            created_by=request.user,
            title=data["title"],
            owner_label=data.get("owner_label", "").strip(),
            priority=data["priority"],
            status=data["status"],
            due_at=data.get("due_at"),
            completed_at=completed_at,
        )
        return Response(_serialize_action_item(item), status=status.HTTP_201_CREATED)


class IncidentActionItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["incidents"],
        request=ActionItemUpdateSerializer,
        responses={200: ActionItemResponseSerializer},
    )
    def patch(self, request, incident_id, item_id):
        incident = get_accessible_incident_or_404(request.user, incident_id, require_write=True)
        item = get_object_or_404(
            IncidentActionItem.objects.select_related("created_by"), pk=item_id, incident=incident
        )
        serializer = ActionItemUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field in ("title", "owner_label", "priority", "due_at"):
            if field in data:
                val = data[field]
                setattr(item, field, val.strip() if isinstance(val, str) else val)
        if "status" in data:
            next_status = data["status"]
            item.status = next_status
            if next_status == IncidentActionItem.Status.DONE and item.completed_at is None:
                item.completed_at = timezone.now()
            elif next_status != IncidentActionItem.Status.DONE:
                item.completed_at = None
        item.save()
        return Response(_serialize_action_item(item))

    @extend_schema(tags=["incidents"], request=None, responses={204: None})
    def delete(self, request, incident_id, item_id):
        incident = get_accessible_incident_or_404(request.user, incident_id, require_write=True)
        item = get_object_or_404(IncidentActionItem, pk=item_id, incident=incident)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
