from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from evidence.models import EvidenceSnapshot
from evidence.selection import SelectionFailure, build_package
from evidence.serializers import (
    EvidencePreviewSerializer,
    EvidenceSelectionSerializer,
    EvidenceSnapshotCreateSerializer,
    EvidenceSnapshotSerializer,
    EvidenceSnapshotSummarySerializer,
)
from incidents.models import Incident
from ingestion.models import LogEvent


class ScopedEvidenceView(APIView):
    permission_classes = [IsAuthenticated]

    def owned_incident(self, incident_id):
        return get_object_or_404(
            Incident, pk=incident_id, owner=self.request.user, deleted_at__isnull=True
        )

    def select(self, incident, validated_ids):
        rows = list(
            LogEvent.objects.filter(incident=incident, pk__in=validated_ids)
            .select_related("source")
            .order_by("pk")
        )
        if len(rows) != len(validated_ids):
            raise SelectionFailure("invalid_scope", "One or more selected events are unavailable.")
        return build_package(str(incident.pk), rows)


class EvidencePreviewView(ScopedEvidenceView):
    @extend_schema(
        request=EvidenceSelectionSerializer,
        responses={200: EvidencePreviewSerializer},
        tags=["evidence"],
    )
    def post(self, request, incident_id):
        incident = self.owned_incident(incident_id)
        serializer = EvidenceSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bundle = self.select(incident, serializer.validated_data["event_ids"])
        except SelectionFailure as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status_code)
        return Response({**bundle, "transmitted": False})


class EvidenceSnapshotListCreateView(ScopedEvidenceView):
    @extend_schema(
        request=None,
        responses={200: EvidenceSnapshotSummarySerializer(many=True)},
        tags=["evidence"],
    )
    def get(self, request, incident_id):
        incident = self.owned_incident(incident_id)
        snapshots = EvidenceSnapshot.objects.filter(incident=incident)[:30]
        return Response([snapshot_data(snapshot, include_entries=False) for snapshot in snapshots])

    @extend_schema(
        request=EvidenceSnapshotCreateSerializer,
        responses={201: EvidenceSnapshotSerializer},
        tags=["evidence"],
    )
    def post(self, request, incident_id):
        incident = self.owned_incident(incident_id)
        serializer = EvidenceSnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # Lock the incident so a concurrent deletion cannot authorize a stale selection.
            with transaction.atomic():
                current = Incident.objects.select_for_update().get(pk=incident.pk)
                if current.deleted_at is not None:
                    return Response({"detail": "Incident not found."}, status=404)
                bundle = self.select(current, serializer.validated_data["event_ids"])
                if bundle["sha256"] != serializer.validated_data["expected_sha256"]:
                    return Response(
                        {"detail": "Evidence changed. Review a new preview."}, status=409
                    )
                snapshot = EvidenceSnapshot.objects.create(
                    incident=current,
                    created_by=request.user,
                    entries=bundle["entries"],
                    sha256=bundle["sha256"],
                    item_count=bundle["event_count"],
                    characters=bundle["characters"],
                    payload_bytes=bundle["payload_bytes"],
                    selection_version=bundle["selection_version"],
                    privacy_policy_version=bundle["privacy_policy_version"],
                    consent_accepted_at=timezone.now(),
                )
        except SelectionFailure as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status_code)
        return Response(snapshot_data(snapshot), status=201)


class EvidenceSnapshotDetailView(ScopedEvidenceView):
    @extend_schema(request=None, responses={200: EvidenceSnapshotSerializer}, tags=["evidence"])
    def get(self, request, incident_id, snapshot_id):
        incident = self.owned_incident(incident_id)
        snapshot = get_object_or_404(EvidenceSnapshot, id=snapshot_id, incident=incident)
        return Response(snapshot_data(snapshot))


def snapshot_data(snapshot, *, include_entries=True):
    result = {
        "id": str(snapshot.id),
        "sha256": snapshot.sha256,
        "event_count": snapshot.item_count,
        "characters": snapshot.characters,
        "payload_bytes": snapshot.payload_bytes,
        "selection_version": snapshot.selection_version,
        "privacy_policy_version": snapshot.privacy_policy_version,
        "consent_accepted_at": snapshot.consent_accepted_at,
        "created_at": snapshot.created_at,
        "transmitted": False,
    }
    if include_entries:
        result["entries"] = snapshot.entries
    return result
