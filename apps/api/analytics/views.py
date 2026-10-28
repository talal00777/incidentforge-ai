from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.engine import EventFact, analyze
from analytics.serializers import AnalysisSerializer
from incidents.models import Incident
from ingestion.models import LogEvent


class IncidentAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter("bucket_minutes", int, required=False, description="1, 5, 15 or 60")
        ],
        responses={200: AnalysisSerializer},
    )
    def get(self, request, incident_id):
        incident = get_object_or_404(
            Incident, pk=incident_id, owner=request.user, deleted_at__isnull=True
        )
        raw_minutes = request.query_params.get("bucket_minutes", "5")
        if raw_minutes not in {"1", "5", "15", "60"}:
            return Response({"detail": "Invalid time bucket"}, status=400)
        rows = list(
            LogEvent.objects.filter(incident=incident)
            .order_by("pk")
            .values_list("id", "occurred_at", "severity", "service", "fingerprint")[:100001]
        )
        if len(rows) > 100000:
            return Response({"detail": "Analysis event limit exceeded"}, status=413)
        events = [
            EventFact(str(id), occurred_at, severity, service, fingerprint)
            for id, occurred_at, severity, service, fingerprint in rows
        ]
        return Response(analyze(events, bucket_minutes=int(raw_minutes)))
