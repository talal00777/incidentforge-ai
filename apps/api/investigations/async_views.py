"""Asynchronous investigation submission, status, and cancellation."""

import hashlib
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from evidence.models import EvidenceSnapshot
from incidents.models import Incident
from investigations.jobs import ACTIVE, cancel_job, enqueue_job, job_data, request_fingerprint
from investigations.models import AIInvestigationJob, AIJobEvent, InvestigationAttempt
from investigations.providers import ProviderFailure, select_provider
from investigations.serializers import InvestigationCreateSerializer
from investigations.validation import snapshot_entries
from investigations.views import InvestigationThrottle

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class AIJobStatusSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    state = serializers.CharField()
    attempt_count = serializers.IntegerField()
    cancel_requested = serializers.BooleanField()
    report_id = serializers.UUIDField(allow_null=True)
    error = serializers.JSONField(allow_null=True)
    available_at = serializers.DateTimeField()
    requested_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)


class PrivateAIJobView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class AIJobListCreateView(PrivateAIJobView):
    def owned_incident(self, request, incident_id):
        return get_object_or_404(
            Incident, id=incident_id, owner=request.user, deleted_at__isnull=True
        )

    @extend_schema(responses={200: AIJobStatusSerializer(many=True)}, tags=["investigations"])
    def get(self, request, incident_id):
        incident = self.owned_incident(request, incident_id)
        jobs = AIInvestigationJob.objects.filter(incident=incident, owner=request.user).order_by(
            "-requested_at"
        )[:20]
        response = Response([job_data(job) for job in jobs])
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=InvestigationCreateSerializer,
        responses={202: AIJobStatusSerializer},
        tags=["investigations"],
    )
    def post(self, request, incident_id):
        incident = self.owned_incident(request, incident_id)
        data_form = InvestigationCreateSerializer(data=request.data)
        data_form.is_valid(raise_exception=True)
        fields = data_form.validated_data
        raw_key = request.headers.get("Idempotency-Key", "")
        if raw_key and not KEY_PATTERN.fullmatch(raw_key):
            return Response(
                {"code": "invalid_idempotency_key", "detail": "Invalid request key."}, status=400
            )
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest() if raw_key else ""
        snapshot = get_object_or_404(EvidenceSnapshot, incident=incident, id=fields["snapshot_id"])
        if fields["transmission_consent"]["snapshot_sha256"] != snapshot.sha256:
            return Response(
                {"code": "stale_consent", "detail": "Review the selected snapshot again."},
                status=409,
            )
        try:
            snapshot_entries(snapshot)
            profile = select_provider(fields["provider"], fields["model_id"])
        except ProviderFailure as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status)
        fingerprint = request_fingerprint(snapshot=snapshot, fields=fields)
        if not InvestigationThrottle().allow_request(request, self):
            return Response(
                {"code": "rate_limited", "detail": "Investigation request limit reached."},
                status=429,
            )
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            # Locking the incident serializes submissions made by the same owner.
            get_object_or_404(
                Incident.objects.select_for_update(),
                pk=incident.pk,
                owner=request.user,
                deleted_at__isnull=True,
            )
            if key_hash:
                previous = AIInvestigationJob.objects.filter(
                    owner=request.user, idempotency_key=key_hash
                ).first()
                if previous:
                    if (
                        previous.request_fingerprint != fingerprint
                        or previous.incident_id != incident.id
                    ):
                        return Response(
                            {
                                "code": "idempotency_conflict",
                                "detail": "Request key is already in use.",
                            },
                            status=409,
                        )
                    return self.accepted(previous)
            if AIInvestigationJob.objects.filter(incident=incident, state__in=ACTIVE).exists():
                return Response(
                    {
                        "code": "investigation_active",
                        "detail": "An investigation is already running for this incident.",
                    },
                    status=409,
                )
            if (
                AIInvestigationJob.objects.filter(owner=request.user, state__in=ACTIVE).count()
                >= settings.AI_JOB_MAX_ACTIVE_PER_OWNER
            ):
                return Response(
                    {"code": "investigation_limit", "detail": "Too many active investigations."},
                    status=429,
                )
            attempt = InvestigationAttempt.objects.create(
                incident=incident,
                snapshot=snapshot,
                created_by=request.user,
                snapshot_sha256=snapshot.sha256,
                provider=profile.name,
                model_id=fields["model_id"],
                prompt_profile=fields["prompt_profile"],
                consent_accepted_at=timezone.now(),
            )
            job = AIInvestigationJob.objects.create(
                incident=incident,
                owner=request.user,
                snapshot=snapshot,
                attempt=attempt,
                idempotency_key=key_hash,
                request_fingerprint=fingerprint,
                provider=profile.name,
                model_id=fields["model_id"],
                prompt_profile=fields["prompt_profile"],
                temperature=fields["temperature"],
                max_output_tokens=int(fields["max_output_tokens"]),
            )
            AIJobEvent.objects.create(
                job=job, actor=request.user, action=AIJobEvent.Action.SUBMITTED
            )
            transaction.on_commit(lambda: enqueue_job(str(job.id)))
        return self.accepted(job)

    def accepted(self, job):
        status_url = f"/api/v1/incidents/{job.incident_id}/ai-runs/{job.id}"
        response = Response(job_data(job), status=202)
        response["Location"] = status_url
        response["Cache-Control"] = "private, no-store"
        return response


class AIJobDetailView(PrivateAIJobView):
    def owned_job(self, request, incident_id, job_id):
        return get_object_or_404(
            AIInvestigationJob,
            pk=job_id,
            incident_id=incident_id,
            incident__owner=request.user,
            owner=request.user,
            incident__deleted_at__isnull=True,
        )

    @extend_schema(responses={200: AIJobStatusSerializer}, tags=["investigations"])
    def get(self, request, incident_id, job_id):
        response = Response(job_data(self.owned_job(request, incident_id, job_id)))
        response["Cache-Control"] = "private, no-store"
        return response


class AIJobCancelView(AIJobDetailView):
    http_method_names = ["post", "options"]

    @extend_schema(request=None, responses={202: AIJobStatusSerializer}, tags=["investigations"])
    def post(self, request, incident_id, job_id):
        job = self.owned_job(request, incident_id, job_id)
        if job.state in {"succeeded", "failed", "cancelled"}:
            return Response(
                {"code": "job_completed", "detail": "Investigation is already complete."},
                status=409,
            )
        job = cancel_job(job.pk, actor=request.user)
        response = Response(job_data(job), status=202)
        response["Cache-Control"] = "private, no-store"
        return response
