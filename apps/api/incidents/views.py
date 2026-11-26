from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, pagination
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from incidents.models import Incident, IncidentAuditEvent
from incidents.serializers import IncidentSerializer
from workspaces.permissions import (
    accessible_incidents_queryset,
    can_delete_incident,
    can_edit_incident,
)
from workspaces.webhooks import dispatch_workspace_webhooks


class IncidentPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class OwnedIncidentMixin:
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentSerializer

    def get_queryset(self):
        return accessible_incidents_queryset(self.request.user).select_related("workspace")


def record_audit(incident, actor, action, fields=()):
    IncidentAuditEvent.objects.create(
        incident=incident, actor=actor, action=action, changed_fields=sorted(fields)
    )


@extend_schema_view(get=extend_schema(tags=["incidents"]), post=extend_schema(tags=["incidents"]))
class IncidentListCreateView(OwnedIncidentMixin, generics.ListCreateAPIView):
    pagination_class = IncidentPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        selected_status = self.request.query_params.get("status")
        if selected_status:
            if selected_status not in Incident.Status.values:
                raise ValidationError({"status": "Invalid incident status"})
            queryset = queryset.filter(status=selected_status)
        workspace_id = self.request.query_params.get("workspace_id", "").strip()
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)
        search = self.request.query_params.get("search", "").strip()
        if len(search) > 100:
            raise ValidationError({"search": "Search must be 100 characters or fewer"})
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(service_name__icontains=search)
                | Q(description__icontains=search)
            )
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        incident = serializer.save(owner=self.request.user)
        record_audit(incident, self.request.user, IncidentAuditEvent.Action.CREATED)
        transaction.on_commit(lambda: dispatch_workspace_webhooks(incident, "incident.created"))


@extend_schema_view(
    get=extend_schema(tags=["incidents"]),
    patch=extend_schema(tags=["incidents"]),
    delete=extend_schema(tags=["incidents"]),
)
class IncidentDetailView(OwnedIncidentMixin, generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    http_method_names = ["get", "patch", "delete", "head", "options"]

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.instance
        if not can_edit_incident(self.request.user, instance):
            raise PermissionDenied("Your workspace role is read-only for this incident.")
        old_status = instance.status
        incident = serializer.save()
        record_audit(
            incident,
            self.request.user,
            IncidentAuditEvent.Action.UPDATED,
            serializer.validated_data.keys(),
        )
        if incident.status != old_status:
            transaction.on_commit(
                lambda: dispatch_workspace_webhooks(incident, "incident.status_changed")
            )

    @transaction.atomic
    def perform_destroy(self, instance):
        if not can_delete_incident(self.request.user, instance):
            raise PermissionDenied("Only incident or workspace owners can delete incidents.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at", "updated_at"])
        record_audit(instance, self.request.user, IncidentAuditEvent.Action.DELETED)
