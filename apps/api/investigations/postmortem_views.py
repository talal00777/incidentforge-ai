"""Authenticated, incident-scoped postmortem version API."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from investigations.models import InvestigationReport, PostmortemVersion
from investigations.postmortem_serializers import (
    PostmortemCreateSerializer,
    PostmortemDetailSerializer,
    PostmortemSummarySerializer,
)
from investigations.postmortem_service import (
    PostmortemConflict,
    create_postmortem,
    verified_content,
)


class ScopedPostmortemView(APIView):
    permission_classes = [IsAuthenticated]

    def owned_incident(self, request, incident_id):
        return get_object_or_404(
            Incident, id=incident_id, owner=request.user, deleted_at__isnull=True
        )


class PostmortemListCreateView(ScopedPostmortemView):
    @extend_schema(responses={200: PostmortemSummarySerializer(many=True)}, tags=["reports"])
    def get(self, request, incident_id):
        incident = self.owned_incident(request, incident_id)
        versions = (
            PostmortemVersion.objects.filter(incident=incident)
            .select_related("review_revision")
            .order_by("-version")[:100]
        )
        return Response(PostmortemSummarySerializer(versions, many=True).data)

    @extend_schema(
        request=PostmortemCreateSerializer,
        responses={200: PostmortemDetailSerializer, 201: PostmortemDetailSerializer},
        tags=["reports"],
    )
    def post(self, request, incident_id):
        incident = self.owned_incident(request, incident_id)
        serializer = PostmortemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        investigation = get_object_or_404(
            InvestigationReport.objects.select_related("snapshot"),
            id=values["investigation_id"],
            incident=incident,
        )
        try:
            version, created = create_postmortem(
                incident=incident,
                investigation=investigation,
                expected_review_revision=values["expected_review_revision"],
                actor=request.user,
            )
        except PostmortemConflict as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=409)
        return Response(PostmortemDetailSerializer(version).data, status=201 if created else 200)


class PostmortemDetailView(ScopedPostmortemView):
    @extend_schema(responses={200: PostmortemDetailSerializer}, tags=["reports"])
    def get(self, request, incident_id, version_id):
        incident = self.owned_incident(request, incident_id)
        version = get_object_or_404(
            PostmortemVersion.objects.select_related("review_revision"),
            id=version_id,
            incident=incident,
        )
        try:
            verified_content(version)
        except PostmortemConflict as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=409)
        return Response(PostmortemDetailSerializer(version).data)
