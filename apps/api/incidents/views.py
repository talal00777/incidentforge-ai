from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, pagination
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from incidents.models import Incident, IncidentAuditEvent
from incidents.serializers import IncidentSerializer


class IncidentPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class OwnedIncidentMixin:
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentSerializer

    def get_queryset(self):
        return Incident.objects.filter(owner=self.request.user, deleted_at__isnull=True)


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
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        incident = serializer.save(owner=self.request.user)
        record_audit(incident, self.request.user, IncidentAuditEvent.Action.CREATED)


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
        incident = serializer.save()
        record_audit(
            incident,
            self.request.user,
            IncidentAuditEvent.Action.UPDATED,
            serializer.validated_data.keys(),
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at", "updated_at"])
        record_audit(instance, self.request.user, IncidentAuditEvent.Action.DELETED)
