from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from evidence.models import EvidenceSnapshot
from incidents.models import Incident
from investigations.models import InvestigationAttempt, InvestigationReport
from investigations.providers import ProviderFailure, public_profiles, select_provider
from investigations.serializers import (
    InvestigationCreateSerializer,
    InvestigationDetailSerializer,
    InvestigationSummarySerializer,
    ProviderOptionSerializer,
)
from investigations.service import run_investigation
from investigations.validation import snapshot_entries


class InvestigationThrottle(UserRateThrottle):
    scope = "investigation_create"
    rate = "20/hour"


class ProviderListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ProviderOptionSerializer(many=True)}, tags=["investigations"])
    def get(self, request):
        return Response(public_profiles())


class ScopedInvestigationView(APIView):
    permission_classes = [IsAuthenticated]

    def owned_incident(self, incident_id):
        return get_object_or_404(
            Incident, id=incident_id, owner=self.request.user, deleted_at__isnull=True
        )


def report_data(record, *, include_report=True):
    result = {
        "id": str(record.id),
        "snapshot_id": str(record.snapshot_id),
        "snapshot_sha256": record.snapshot_sha256,
        "provider": record.provider,
        "model_id": record.model_id,
        "temperature": record.temperature,
        "max_output_tokens": record.max_output_tokens,
        "prompt_profile": record.prompt_profile,
        "prompt_version": record.prompt_version,
        "response_schema_version": record.response_schema_version,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "consent_accepted_at": record.consent_accepted_at,
        "created_at": record.created_at,
    }
    if include_report:
        result["report"] = record.report
    return result


class InvestigationListCreateView(ScopedInvestigationView):
    @extend_schema(
        responses={200: InvestigationSummarySerializer(many=True)}, tags=["investigations"]
    )
    def get(self, request, incident_id):
        incident = self.owned_incident(incident_id)
        reports = InvestigationReport.objects.filter(incident=incident)[:30]
        return Response([report_data(item, include_report=False) for item in reports])

    @extend_schema(
        request=InvestigationCreateSerializer,
        responses={201: InvestigationDetailSerializer},
        tags=["investigations"],
    )
    def post(self, request, incident_id):
        incident = self.owned_incident(incident_id)
        # Explicit per-request consent is evaluated before even resolving provider configuration.
        serializer = InvestigationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not InvestigationThrottle().allow_request(request, self):
            return Response(
                {"code": "rate_limited", "detail": "Investigation request limit reached."},
                status=429,
            )
        data = serializer.validated_data
        snapshot = get_object_or_404(EvidenceSnapshot, incident=incident, id=data["snapshot_id"])
        if data["transmission_consent"]["snapshot_sha256"] != snapshot.sha256:
            return Response(
                {"code": "stale_consent", "detail": "Review the selected snapshot again."},
                status=409,
            )
        try:
            entries = snapshot_entries(snapshot)
            profile = select_provider(data["provider"], data["model_id"])
        except ProviderFailure as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status)

        consent_time = timezone.now()
        attempt = InvestigationAttempt.objects.create(
            incident=incident,
            snapshot=snapshot,
            created_by=request.user,
            snapshot_sha256=snapshot.sha256,
            provider=profile.name,
            model_id=data["model_id"],
            prompt_profile=data["prompt_profile"],
            consent_accepted_at=consent_time,
        )
        try:
            # Only redacted immutable entries are transmitted; never raw source files.
            report, usage, version = run_investigation(
                provider=profile,
                model=data["model_id"],
                entries=entries,
                temperature=data["temperature"],
                max_tokens=int(data["max_output_tokens"]),
                prompt_profile=data["prompt_profile"],
            )
        except ProviderFailure as exc:
            attempt.status = "failed"
            attempt.failure_code = exc.code
            attempt.save(update_fields=["status", "failure_code", "updated_at"])
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status)
        saved = InvestigationReport.objects.create(
            attempt=attempt,
            incident=incident,
            snapshot=snapshot,
            created_by=request.user,
            snapshot_sha256=snapshot.sha256,
            provider=profile.name,
            model_id=data["model_id"],
            temperature=data["temperature"],
            max_output_tokens=int(data["max_output_tokens"]),
            prompt_profile=data["prompt_profile"],
            prompt_version=version,
            response_schema_version=report["schema_version"],
            report=report,
            input_tokens=usage["prompt_tokens"] or None,
            output_tokens=usage["completion_tokens"] or None,
            consent_accepted_at=consent_time,
        )
        attempt.status = "succeeded"
        attempt.save(update_fields=["status", "updated_at"])
        return Response(report_data(saved), status=201)


class InvestigationDetailView(ScopedInvestigationView):
    @extend_schema(responses={200: InvestigationDetailSerializer}, tags=["investigations"])
    def get(self, request, incident_id, report_id):
        incident = self.owned_incident(incident_id)
        report = get_object_or_404(InvestigationReport, id=report_id, incident=incident)
        return Response(report_data(report))
