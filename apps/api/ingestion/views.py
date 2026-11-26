import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q
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
    EventContextResponseSerializer,
    EventFacetsResponseSerializer,
    IngestionJobStatusSerializer,
    PaginatedEventsSerializer,
    SourceSummarySerializer,
    UploadAcceptedSerializer,
    UploadRequestSerializer,
)
from ingestion.storage import path_for, store
from ingestion.tasks import process_ingestion
from workspaces.permissions import get_accessible_incident_or_404

logger = logging.getLogger(__name__)

NESTED_QUANTIFIER_RE = re.compile(r"\([^)]*[+*][^)]*\)[+*?{]")


def enqueue_ingestion(job_id):
    try:
        process_ingestion.delay(job_id)
    except Exception:
        logger.warning("Unable to enqueue ingestion job %s; reconciliation will retry", job_id)


def _serialize_event(item: LogEvent) -> dict:
    return {
        "id": str(item.id),
        "source_id": str(item.source_id),
        "line_start": item.line_start,
        "line_end": item.line_end,
        "occurred_at": item.occurred_at,
        "observed_at": item.observed_at,
        "timestamp_quality": item.timestamp_quality,
        "severity": item.severity,
        "service": item.service,
        "trace_id": item.trace_id,
        "message": item.redacted_message,
        "fingerprint": item.fingerprint,
    }


def _validate_safe_regex(pattern: str) -> str:
    if len(pattern) > 80:
        raise ValidationError({"search": "Regex search must be 80 characters or fewer."})
    if NESTED_QUANTIFIER_RE.search(pattern):
        raise ValidationError({"search": "Nested quantifiers are not allowed in regex search."})
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValidationError({"search": f"Invalid regular expression: {exc}."}) from exc
    return pattern


class OwnedIncidentView(APIView):
    permission_classes = [IsAuthenticated]

    def incident(self, incident_id, *, require_write: bool = False):
        return get_accessible_incident_or_404(
            self.request.user, incident_id, require_write=require_write
        )


class UploadView(OwnedIncidentView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=UploadRequestSerializer,
        responses={202: UploadAcceptedSerializer},
    )
    def post(self, request, incident_id):
        incident = self.incident(incident_id, require_write=True)
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
            OpenApiParameter("trace_id", OpenApiTypes.STR, required=False),
            OpenApiParameter("fingerprint", OpenApiTypes.STR, required=False),
            OpenApiParameter("search", OpenApiTypes.STR, required=False),
            OpenApiParameter("regex", OpenApiTypes.BOOL, required=False),
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
        trace_id = request.query_params.get("trace_id", "").strip()
        if trace_id:
            events = events.filter(trace_id=trace_id[:128])
        fingerprint = request.query_params.get("fingerprint", "").strip()
        if fingerprint:
            events = events.filter(fingerprint=fingerprint[:64])
        search = request.query_params.get("search", "").strip()
        use_regex = request.query_params.get("regex", "").strip().lower() in ("1", "true", "yes")
        if search:
            if use_regex:
                pattern = _validate_safe_regex(search)
                events = events.filter(redacted_message__iregex=pattern)
            else:
                if len(search) > 100:
                    raise ValidationError({"search": "Search must be 100 characters or fewer."})
                events = events.filter(
                    Q(redacted_message__icontains=search)
                    | Q(service__icontains=search)
                    | Q(trace_id__icontains=search)
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
        return page.get_paginated_response([_serialize_event(item) for item in records])


class EventFacetsView(OwnedIncidentView):
    @extend_schema(
        tags=["ingestion"],
        request=None,
        responses={200: EventFacetsResponseSerializer},
    )
    def get(self, request, incident_id):
        incident = self.incident(incident_id)
        base = LogEvent.objects.filter(incident=incident)
        total = base.count()

        severities = [
            {"value": row["severity"] or "UNKNOWN", "count": row["count"]}
            for row in base.values("severity")
            .annotate(count=Count("id"))
            .order_by("-count", "severity")[:12]
        ]
        services = [
            {"value": row["service"], "count": row["count"]}
            for row in base.exclude(service="")
            .values("service")
            .annotate(count=Count("id"))
            .order_by("-count", "service")[:16]
        ]
        sources = [
            {
                "id": str(row["source_id"]),
                "filename": row["source__filename"],
                "count": row["count"],
            }
            for row in base.values("source_id", "source__filename")
            .annotate(count=Count("id"))
            .order_by("-count", "source__filename")[:20]
        ]

        fp_rows = list(
            base.exclude(fingerprint="")
            .values("fingerprint")
            .annotate(count=Count("id"))
            .order_by("-count", "fingerprint")[:8]
        )
        top_fingerprints = []
        if fp_rows:
            fp_keys = [row["fingerprint"] for row in fp_rows]
            samples: dict[str, LogEvent] = {}
            for ev in (
                base.filter(fingerprint__in=fp_keys)
                .only("fingerprint", "redacted_message", "severity", "service")
                .order_by("fingerprint", "-observed_at")
            ):
                if ev.fingerprint not in samples:
                    samples[ev.fingerprint] = ev
            for row in fp_rows:
                sample = samples.get(row["fingerprint"])
                top_fingerprints.append(
                    {
                        "fingerprint": row["fingerprint"],
                        "count": row["count"],
                        "sample_message": (sample.redacted_message[:180] if sample else ""),
                        "severity": sample.severity if sample else "",
                        "service": sample.service if sample else "",
                    }
                )

        return Response(
            {
                "total_events": total,
                "severities": severities,
                "services": services,
                "sources": sources,
                "top_fingerprints": top_fingerprints,
            }
        )


class EventContextView(OwnedIncidentView):
    @extend_schema(
        tags=["ingestion"],
        request=None,
        parameters=[
            OpenApiParameter(
                "window",
                OpenApiTypes.INT,
                required=False,
                description="Number of surrounding log records before and after (1-25, default 10).",
            )
        ],
        responses={200: EventContextResponseSerializer},
    )
    def get(self, request, incident_id, event_id):
        incident = self.incident(incident_id)
        event = get_object_or_404(
            LogEvent.objects.select_related("source"), id=event_id, incident=incident
        )
        raw_window = request.query_params.get("window", "10").strip()
        try:
            window = max(1, min(25, int(raw_window)))
        except ValueError as exc:
            raise ValidationError(
                {"window": "Window must be an integer between 1 and 25."}
            ) from exc

        before_desc = list(
            LogEvent.objects.filter(
                incident=incident,
                source_id=event.source_id,
                line_start__lt=event.line_start,
            ).order_by("-line_start", "-id")[:window]
        )
        before_desc.reverse()

        after_asc = list(
            LogEvent.objects.filter(
                incident=incident,
                source_id=event.source_id,
                line_start__gt=event.line_start,
            ).order_by("line_start", "id")[:window]
        )

        related_trace_count = (
            LogEvent.objects.filter(incident=incident, trace_id=event.trace_id).count()
            if event.trace_id
            else 0
        )
        same_fingerprint_count = (
            LogEvent.objects.filter(incident=incident, fingerprint=event.fingerprint).count()
            if event.fingerprint
            else 0
        )

        detail = _serialize_event(event)
        detail["source_filename"] = event.source.filename
        detail["source_sha256"] = event.source.sha256
        detail["parser_version"] = event.parser_version

        return Response(
            {
                "event": detail,
                "before": [_serialize_event(item) for item in before_desc],
                "after": [_serialize_event(item) for item in after_asc],
                "window": window,
                "related_trace_count": related_trace_count,
                "same_fingerprint_count": same_fingerprint_count,
            }
        )
