from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import pagination, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.storage import path_for, store
from ingestion.tasks import process_ingestion


class OwnedIncidentView(APIView):
    permission_classes = [IsAuthenticated]

    def incident(self, incident_id):
        return get_object_or_404(Incident, id=incident_id, owner=self.request.user, deleted_at__isnull=True)


class UploadView(OwnedIncidentView):
    parser_classes = [MultiPartParser]

    def post(self, request, incident_id):
        incident = self.incident(incident_id)
        files = request.FILES.getlist("files")
        if not 1 <= len(files) <= settings.INGESTION_MAX_FILES:
            return Response({"detail": "Upload between 1 and 5 files."}, status=400)
        for upload in files:
            filename = upload.name.lower()
            if not filename.endswith((".log", ".txt", ".jsonl")):
                return Response({"detail": "Allowed file types: .log, .txt, .jsonl."}, status=400)
            if upload.size > settings.INGESTION_MAX_FILE_BYTES or upload.size == 0:
                return Response({"detail": "File exceeds the configured size limit or is empty."}, status=400)
            sample = upload.read(min(4096, upload.size))
            upload.seek(0)
            if b"\x00" in sample:
                return Response({"detail": "Binary content is not accepted."}, status=400)
        with transaction.atomic():
            Incident.objects.select_for_update().get(pk=incident.pk)
            active = IngestionJob.objects.filter(incident=incident, state__in=["queued", "running"]).exists()
            if active:
                return Response({"detail": "An ingestion job is already active."}, status=409)
            job = IngestionJob.objects.create(incident=incident, owner=request.user)
            keys = []
            try:
                for upload in files:
                    key, sha, size = store(upload)
                    keys.append(key)
                    LogSource.objects.create(incident=incident, job=job, filename=upload.name[:255], object_key=key, sha256=sha, byte_size=size)
            except Exception:
                for key in keys:
                    path_for(key).unlink(missing_ok=True)
                raise
            transaction.on_commit(lambda: process_ingestion.delay(str(job.id)))
        return Response({"job_id": str(job.id), "state": job.state, "source_ids": [str(source.id) for source in job.sources.all()]}, status=status.HTTP_202_ACCEPTED)


class SourcesView(OwnedIncidentView):
    def get(self, request, incident_id):
        incident = self.incident(incident_id)
        return Response([{"id": str(item.id), "filename": item.filename, "sha256": item.sha256, "byte_size": item.byte_size, "state": item.state, "accepted": item.accepted, "rejected": item.rejected, "warnings": item.warnings} for item in LogSource.objects.filter(incident=incident).order_by("-created_at")[:100]])


class JobsView(OwnedIncidentView):
    def get(self, request, incident_id, job_id):
        incident = self.incident(incident_id)
        item = get_object_or_404(IngestionJob, id=job_id, incident=incident)
        return Response({"id": str(item.id), "state": item.state, "accepted": item.accepted, "rejected": item.rejected, "error_code": item.error_code})


class EventPagination(pagination.PageNumberPagination):
    page_size = 50
    max_page_size = 100
    page_size_query_param = "page_size"


class EventsView(OwnedIncidentView):
    def get(self, request, incident_id):
        incident = self.incident(incident_id)
        events = LogEvent.objects.filter(incident=incident).order_by("-observed_at", "-id")
        severity = request.query_params.get("severity")
        if severity:
            events = events.filter(severity=severity.upper()[:16])
        page = EventPagination()
        records = page.paginate_queryset(events, request, view=self)
        return page.get_paginated_response([{"id": str(item.id), "source_id": str(item.source_id), "line_start": item.line_start, "line_end": item.line_end, "occurred_at": item.occurred_at, "observed_at": item.observed_at, "timestamp_quality": item.timestamp_quality, "severity": item.severity, "service": item.service, "message": item.redacted_message, "fingerprint": item.fingerprint} for item in records])
