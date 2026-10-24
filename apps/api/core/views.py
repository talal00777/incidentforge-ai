"""Versioned foundation API endpoints and container health probes."""

from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.health import dependencies_ready


def liveness(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    return JsonResponse({"status": "alive"})


def readiness(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    ready = dependencies_ready()
    return JsonResponse(
        {"status": "ready" if ready else "unavailable"}, status=200 if ready else 503
    )


class SystemInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    api_version = serializers.CharField()
    milestone = serializers.CharField()
    capabilities = serializers.ListField(child=serializers.CharField())


class SystemInfoView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: SystemInfoSerializer}, tags=["system"])
    def get(self, request):
        return Response(
            {
                "name": "IncidentForge AI",
                "api_version": "v1",
                "milestone": "M0",
                "capabilities": ["health", "openapi"],
            }
        )
