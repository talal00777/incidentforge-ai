"""Owner-scoped human review endpoint with optimistic revision concurrency."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from investigations.models import (
    InvestigationReport,
    InvestigationReview,
    InvestigationReviewRevision,
)
from investigations.review_serializers import ReviewResponseSerializer, ReviewUpdateSerializer


def initial_review(report):
    return {
        "revision": 0,
        "status": "draft",
        "impact_notes": "",
        "remediation_notes": "",
        "hypotheses": [
            {"index": index, "decision": "needs_review", "note": ""}
            for index, _ in enumerate(report.report.get("hypotheses", []))
        ],
        "updated_at": None,
    }


def latest_review(report):
    try:
        review = InvestigationReview.objects.get(report=report)
    except InvestigationReview.DoesNotExist:
        return initial_review(report)
    current = review.revisions.order_by("-number").first()
    if current is None:
        return initial_review(report)
    return {
        "revision": current.number,
        "status": current.status,
        "impact_notes": current.impact_notes,
        "remediation_notes": current.remediation_notes,
        "hypotheses": current.hypotheses,
        "updated_at": current.created_at,
    }


class InvestigationReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def owned_report(self, request, incident_id, report_id):
        incident = get_object_or_404(
            Incident, id=incident_id, owner=request.user, deleted_at__isnull=True
        )
        return get_object_or_404(InvestigationReport, id=report_id, incident=incident)

    @extend_schema(responses={200: ReviewResponseSerializer}, tags=["investigations"])
    def get(self, request, incident_id, report_id):
        report = self.owned_report(request, incident_id, report_id)
        return Response(latest_review(report))

    @extend_schema(
        request=ReviewUpdateSerializer,
        responses={200: ReviewResponseSerializer},
        tags=["investigations"],
    )
    def put(self, request, incident_id, report_id):
        report = self.owned_report(request, incident_id, report_id)
        serializer = ReviewUpdateSerializer(
            data=request.data,
            context={"hypothesis_count": len(report.report.get("hypotheses", []))},
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            review, _ = InvestigationReview.objects.get_or_create(
                report=report, defaults={"created_by": request.user}
            )
            review = InvestigationReview.objects.select_for_update().get(pk=review.pk)
            if values["expected_revision"] != review.latest_revision:
                return Response(
                    {
                        "code": "review_conflict",
                        "detail": "This review changed. Reload before saving.",
                    },
                    status=409,
                )
            next_number = review.latest_revision + 1
            InvestigationReviewRevision.objects.create(
                review=review,
                number=next_number,
                author=request.user,
                status=values["status"],
                impact_notes=values["impact_notes"],
                remediation_notes=values["remediation_notes"],
                hypotheses=values["hypotheses"],
            )
            review.latest_revision = next_number
            review.save(update_fields=["latest_revision", "updated_at"])
        return Response(latest_review(report))
