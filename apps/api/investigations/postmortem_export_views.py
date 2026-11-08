"""Authenticated, incident-owned exports of immutable postmortem versions."""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from investigations.models import PostmortemVersion
from investigations.postmortem_export import (
    PostmortemExportError,
    export_envelope,
    render_json,
    render_pdf,
)
from investigations.postmortem_service import PostmortemConflict, verified_content
from investigations.postmortem_views import ScopedPostmortemView

logger = logging.getLogger(__name__)


class PostmortemDownloadView(ScopedPostmortemView):
    """Stream an authorized version as PDF or canonical JSON without storing public files."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="export_format",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=["pdf", "json"],
                required=False,
                description="Export format; defaults to pdf.",
            ),
        ],
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (200, "application/json"): OpenApiTypes.BINARY,
        },
        tags=["reports"],
    )
    def get(self, request, incident_id, version_id):
        export_format = request.query_params.get("export_format", "pdf")
        if export_format not in ("pdf", "json"):
            return Response(
                {"code": "invalid_export_format", "detail": "Choose pdf or json."},
                status=400,
            )
        incident = self.owned_incident(request, incident_id)
        version = get_object_or_404(
            PostmortemVersion.objects.select_related("review_revision"),
            id=version_id,
            incident=incident,
        )
        try:
            envelope = export_envelope(version=version, verified_content=verified_content(version))
            data = render_json(envelope) if export_format == "json" else render_pdf(envelope)
        except PostmortemConflict as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=409)
        except PostmortemExportError as exc:
            status = 409 if exc.code == "report_integrity" else 422
            return Response({"code": exc.code, "detail": exc.message}, status=status)
        except Exception:
            logger.exception(
                "Postmortem export failed: incident=%s version=%s", incident.pk, version.pk
            )
            return Response(
                {
                    "code": "export_unavailable",
                    "detail": "The report download is temporarily unavailable.",
                },
                status=503,
            )

        content_type = "application/pdf" if export_format == "pdf" else "application/json"
        suffix = "pdf" if export_format == "pdf" else "json"
        filename = f"incidentforge-postmortem-v{version.version}-{version.id}.{suffix}"
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(len(data))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
