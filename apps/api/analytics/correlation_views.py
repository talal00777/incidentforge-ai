from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.correlation import MAX_INPUT_EVENTS, CorrelationEvent, correlate
from analytics.correlation_serializers import CorrelationSerializer
from incidents.models import Incident
from ingestion.models import LogEvent


class IncidentRelationshipsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: CorrelationSerializer})
    def get(self, request, incident_id):
        incident = get_object_or_404(
            Incident, pk=incident_id, owner=request.user, deleted_at__isnull=True
        )
        rows = list(
            LogEvent.objects.filter(incident=incident)
            .order_by("id")
            .values_list(
                "id",
                "source_id",
                "line_start",
                "line_end",
                "occurred_at",
                "timestamp_quality",
                "severity",
                "service",
                "trace_id",
                "redacted_message",
            )[: MAX_INPUT_EVENTS + 1]
        )
        if len(rows) > MAX_INPUT_EVENTS:
            return Response({"detail": "Correlation event limit exceeded"}, status=413)
        facts = [
            CorrelationEvent(
                id=str(row[0]),
                source_id=str(row[1]),
                line_start=row[2],
                line_end=row[3],
                occurred_at=row[4],
                timestamp_quality=row[5],
                severity=row[6],
                service=row[7],
                trace_id=row[8],
                redacted_message=row[9],
            )
            for row in rows
        ]
        return Response(correlate(facts))
