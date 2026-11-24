"""Operational dashboard summary and synthetic demo scenario API views."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from incidents.dashboard import build_dashboard_summary
from incidents.demo_seeder import SCENARIOS_BY_ID, list_demo_scenarios, seed_demo_scenario
from incidents.serializers import IncidentSerializer


class DashboardCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    open = serializers.IntegerField()
    investigating = serializers.IntegerField()
    resolved = serializers.IntegerField()
    archived = serializers.IntegerField()
    critical_open = serializers.IntegerField()
    high_open = serializers.IntegerField()


class DashboardSeveritySerializer(serializers.Serializer):
    severity = serializers.CharField()
    count = serializers.IntegerField()
    open_count = serializers.IntegerField()


class DashboardTelemetryTotalsSerializer(serializers.Serializer):
    total_sources = serializers.IntegerField()
    total_events = serializers.IntegerField()
    total_error_events = serializers.IntegerField()
    total_snapshots = serializers.IntegerField()
    total_investigations = serializers.IntegerField()
    total_postmortems = serializers.IntegerField()


class DashboardServiceHealthSerializer(serializers.Serializer):
    service = serializers.CharField()
    incident_count = serializers.IntegerField()
    event_count = serializers.IntegerField()
    error_events = serializers.IntegerField()


class DashboardRecentIncidentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    service_name = serializers.CharField()
    environment = serializers.CharField()
    severity = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    source_count = serializers.IntegerField()
    event_count = serializers.IntegerField()
    error_count = serializers.IntegerField()
    investigation_count = serializers.IntegerField()
    postmortem_count = serializers.IntegerField()


class DashboardActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    summary = serializers.CharField()
    incident_id = serializers.UUIDField()
    incident_title = serializers.CharField()
    occurred_at = serializers.DateTimeField()


class DashboardSummarySerializer(serializers.Serializer):
    counts = DashboardCountsSerializer()
    severity_breakdown = DashboardSeveritySerializer(many=True)
    telemetry_totals = DashboardTelemetryTotalsSerializer()
    mttr_minutes = serializers.FloatField(allow_null=True)
    service_health = DashboardServiceHealthSerializer(many=True)
    recent_incidents = DashboardRecentIncidentSerializer(many=True)
    recent_activity = DashboardActivitySerializer(many=True)


class DemoScenarioSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    service_name = serializers.CharField()
    environment = serializers.CharField()
    severity = serializers.CharField()
    services = serializers.ListField(child=serializers.CharField())
    expected_signals = serializers.ListField(child=serializers.CharField())


class DemoSeedRequestSerializer(serializers.Serializer):
    scenario_id = serializers.ChoiceField(choices=tuple(SCENARIOS_BY_ID.keys()))


class DemoSeedResultSerializer(serializers.Serializer):
    scenario_id = serializers.CharField()
    incident = IncidentSerializer()
    sources_created = serializers.IntegerField()
    events_created = serializers.IntegerField()
    snapshot_id = serializers.UUIDField()


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: DashboardSummarySerializer}, tags=["incidents"])
    def get(self, request):
        data = build_dashboard_summary(request.user)
        return Response(DashboardSummarySerializer(data).data)


class DemoScenarioListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"

    @extend_schema(responses={200: DemoScenarioSerializer(many=True)}, tags=["incidents"])
    def get(self, request):
        return Response(DemoScenarioSerializer(list_demo_scenarios(), many=True).data)

    @extend_schema(
        request=DemoSeedRequestSerializer,
        responses={201: DemoSeedResultSerializer},
        tags=["incidents"],
    )
    def post(self, request):
        serializer = DemoSeedRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            seeded = seed_demo_scenario(request.user, serializer.validated_data["scenario_id"])
        except ValueError as exc:
            raise ValidationError({"scenario_id": str(exc)}) from None
        return Response(DemoSeedResultSerializer(seeded).data, status=status.HTTP_201_CREATED)
