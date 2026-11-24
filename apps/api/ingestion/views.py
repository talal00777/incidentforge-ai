import logging
from datetime import UTC, datetime
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import pagination, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.security import UploadRejected, validate_upload
from ingestion.serializers import (
    IngestionJobStatusSerializer,
    PaginatedEventsSerializer,
    SourceSummarySerializer,
    UploadAcceptedSerializer,
    UploadRequestSerializer,
)
from ingestion.storage import path_for, store
from ingestion.tasks import process_ingestion

logger = logging.getLogger(__name__)


def enqueue_ingestion(job_id):
    try:
        process_ingestion.delay(job_id)
    except Exception:
        logger.warning("Unable to enqueue ingestion job %s; reconciliation will retry", job_id)


class OwnedIncidentView(APIView):
    permission_classes = [IsAuthenticated]

    def incident(self, incident_id):
        return get_object_or_404(
            Incident, id=incident_id, owner=self.request.user, deleted_at__isnull=True
        )


class UploadView(OwnedIncidentView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=UploadRequestSerializer,
        responses={202: UploadAcceptedSerializer},
    )
    def post(self, request, incident_id):
        incident = self.incident(incident_id)
        files = request.FILES.getlist("files")
        if not 1 <= len(files) <= settings.INGESTION_MAX_FILES:
            return Response({"detail": "Upload between 1 and 5 files."}, status=400)
        validated_names = []
        try:
            for upload in files:
                validated_names.append(validate_upload(upload))
        except UploadRejected as exc:
            return Response({"code": exc.code, "detail": str(exc)}, status=400)
        with transaction.atomic():
            Incident.objects.select_for_update().get(pk=incident.pk)
            active = IngestionJob.objects.filter(
                incident=incident, state__in=["queued", "running"]
            ).exists()
            if active:
                return Response({"detail": "An ingestion job is already active."}, status=409)
            job = IngestionJob.objects.create(incident=incident, owner=request.user)
            keys = []
            try:
                for upload, filename in zip(files, validated_names, strict=True):
                    key, sha, size = store(upload)
                    keys.append(key)
                    LogSource.objects.create(
                        incident=incident,
                        job=job,
                        filename=filename,
                        object_key=key,
                        sha256=sha,
                        byte_size=size,
                    )
            except Exception:
                for key in keys:
                    path_for(key).unlink(missing_ok=True)
                raise
            transaction.on_commit(lambda: enqueue_ingestion(str(job.id)))
        return Response(
            {
                "job_id": str(job.id),
                "state": job.state,
                "source_ids": [str(source.id) for source in job.sources.all()],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SourcesView(OwnedIncidentView):
    @extend_schema(request=None, responses={200: SourceSummarySerializer(many=True)})
    def get(self, request, incident_id):
        incident = self.incident(incident_id)
        return Response(
            [
                {
                    "id": str(item.id),
                    "filename": item.filename,
                    "sha256": item.sha256,
                    "byte_size": item.byte_size,
                    "state": item.state,
                    "accepted": item.accepted,
                    "rejected": item.rejected,
                    "warnings": item.warnings,
                }
                for item in LogSource.objects.filter(incident=incident).order_by("-created_at")[
                    :100
                ]
            ]
        )


class JobsView(OwnedIncidentView):
    @extend_schema(request=None, responses={200: IngestionJobStatusSerializer})
    def get(self, request, incident_id, job_id):
        incident = self.incident(incident_id)
        item = get_object_or_404(IngestionJob, id=job_id, incident=incident)
        return Response(
            {
                "id": str(item.id),
                "state": item.state,
                "accepted": item.accepted,
                "rejected": item.rejected,
                "error_code": item.error_code,
            }
        )


class EventPagination(pagination.PageNumberPagination):
    page_size = 50
    max_page_size = 100
    page_size_query_param = "page_size"


def _parse_iso_utc(value: str, field: str) -> datetime:
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError({field: "Enter a valid ISO-8601 timestamp with timezone."}) from exc
    if parsed.tzinfo is None:
        raise ValidationError({field: "Timestamp filter must include a timezone offset."})
    return parsed.astimezone(UTC)


class EventsView(OwnedIncidentView):
    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, required=False),
            OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
            OpenApiParameter("severity", OpenApiTypes.STR, required=False),
            OpenApiParameter("service", OpenApiTypes.STR, required=False),
            OpenApiParameter("source_id", OpenApiTypes.UUID, required=False),
            OpenApiParameter("search", OpenApiTypes.STR, required=False),
            OpenApiParameter("from", OpenApiTypes.DATETIME, required=False),
            OpenApiParameter("to", OpenApiTypes.DATETIME, required=False),
            OpenApiParameter(
                "sort",
                OpenApiTypes.STR,
                required=False,
                enum=["observed_desc", "occurred_desc", "occurred_asc", "source"],
            ),
        ],
        responses={200: PaginatedEventsSerializer},
    )
    def get(self, request, incident_id):
        incident = self.incident(incident_id)
        events = LogEvent.objects.filter(incident=incident)
        severity = request.query_params.get("severity")
        if severity:
            events = events.filter(severity=severity.strip().upper()[:16])
        service = request.query_params.get("service", "").strip()
        if service:
            events = events.filter(service__iexact=service[:120])
        source_id = request.query_params.get("source_id", "").strip()
        if source_id:
            try:
                parsed_source = UUID(source_id)
            except ValueError as exc:
                raise ValidationError({"source_id": "Enter a valid source UUID."}) from exc
            events = events.filter(source_id=parsed_source)
        search = request.query_params.get("search", "").strip()
        if len(search) > 100:
            raise ValidationError({"search": "Search must be 100 characters or fewer."})
        if search:
            events = events.filter(
                Q(redacted_message__icontains=search) | Q(service__icontains=search)
            )
        from_raw = request.query_params.get("from", "").strip()
        if from_raw:
            events = events.filter(occurred_at__gte=_parse_iso_utc(from_raw, "from"))
        to_raw = request.query_params.get("to", "").strip()
        if to_raw:
            events = events.filter(occurred_at__lte=_parse_iso_utc(to_raw, "to"))
        sort = request.query_params.get("sort", "observed_desc").strip()
        if sort == "observed_desc":
            events = events.order_by("-observed_at", "-id")
        elif sort == "occurred_desc":
            events = events.order_by(F("occurred_at").desc(nulls_last=True), "-id")
        elif sort == "occurred_asc":
            events = events.order_by(F("occurred_at").asc(nulls_last=True), "id")
        elif sort == "source":
            events = events.order_by("source_id", "line_start", "id")
        else:
            raise ValidationError(
                {"sort": "Choose observed_desc, occurred_desc, occurred_asc, or source."}
            )
        page = EventPagination()
        records = page.paginate_queryset(events, request, view=self)
        return page.get_paginated_response(
            [
                {
                    "id": str(item.id),
                    "source_id": str(item.source_id),
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "occurred_at": item.occurred_at,
                    "observed_at": item.observed_at,
                    "timestamp_quality": item.timestamp_quality,
                    "severity": item.severity,
                    "service": item.service,
                    "message": item.redacted_message,
                    "fingerprint": item.fingerprint,
                }
                for item in records
            ]
        )
