"""Authenticated rendering of deterministic incident charts."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.charting import CHART_TYPES, render_png
from analytics.engine import MAX_EVENTS, EventFact, analyze
from incidents.models import Incident
from ingestion.models import LogEvent


class IncidentChartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        parameters=[OpenApiParameter("bucket_minutes", int, required=False)],
        responses={
            (200, "image/png"): OpenApiResponse(response=OpenApiTypes.BINARY),
            400: OpenApiResponse(description="Invalid chart or bucket size"),
            413: OpenApiResponse(description="Incident analysis size limit exceeded"),
        },
    )
    def get(self, request, incident_id, chart_type):
        incident = get_object_or_404(
            Incident, pk=incident_id, owner=request.user, deleted_at__isnull=True
        )
        bucket = request.query_params.get("bucket_minutes", "5")
        if bucket not in {"1", "5", "15", "60"} or chart_type not in CHART_TYPES:
            return Response({"detail": "Unsupported chart configuration"}, status=400)
        rows = list(
            LogEvent.objects.filter(incident=incident)
            .order_by("pk")
            .values_list("id", "occurred_at", "severity", "service", "fingerprint")[
                : MAX_EVENTS + 1
            ]
        )
        if len(rows) > MAX_EVENTS:
            return Response({"detail": "Analysis event limit exceeded"}, status=413)
        events = [
            EventFact(str(id), occurred_at, severity, service, fingerprint)
            for id, occurred_at, severity, service, fingerprint in rows
        ]
        analysis = analyze(events, bucket_minutes=int(bucket))
        response = HttpResponse(render_png(chart_type, analysis, events), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
