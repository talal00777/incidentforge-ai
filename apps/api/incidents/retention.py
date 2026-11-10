from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from incidents.models import Incident, ReportPurgeReceipt
from ingestion.models import IngestionJob
from investigations.models import (
    InvestigationAttempt,
    InvestigationReport,
    InvestigationReview,
    InvestigationReviewRevision,
    PostmortemVersion,
)

ACTIVE_JOBS = (IngestionJob.State.QUEUED, IngestionJob.State.RUNNING)


@transaction.atomic
def purge_report_content(incident_id, *, cutoff, retention_days, execute):
    incident = Incident.objects.select_for_update().filter(pk=incident_id).first()
    if incident is None or incident.deleted_at is None or incident.deleted_at > cutoff:
        return "ineligible", None
    if ReportPurgeReceipt.objects.filter(incident=incident).exists():
        return "complete", None
    if IngestionJob.objects.filter(incident=incident, state__in=ACTIVE_JOBS).exists():
        return "active", None

    reports = InvestigationReport.objects.filter(incident=incident)
    reviews = InvestigationReview.objects.filter(report__incident=incident)
    revisions = InvestigationReviewRevision.objects.filter(review__report__incident=incident)
    versions = PostmortemVersion.objects.filter(incident=incident)
    attempts = InvestigationAttempt.objects.filter(incident=incident)
    snapshots = EvidenceSnapshot.objects.filter(incident=incident)
    counts = {
        "postmortems": versions.count(),
        "review_revisions": revisions.count(),
        "reviews": reviews.count(),
        "reports": reports.count(),
        "attempts": attempts.count(),
        "snapshots": snapshots.count(),
    }
    if execute:
        versions.delete()
        revisions.delete()
        reviews.delete()
        reports.delete()
        attempts.delete()
        snapshots.delete()
        Incident.objects.filter(pk=incident.pk).update(
            title="Deleted incident",
            description="",
            service_name="",
            impact_notes="",
            environment=Incident.Environment.OTHER,
            severity=Incident.Severity.MEDIUM,
            status=Incident.Status.ARCHIVED,
            timezone="UTC",
        )
        ReportPurgeReceipt.objects.create(
            incident=incident, retention_days=retention_days, **counts
        )
    return "eligible", counts


def retention_cutoff(days):
    return timezone.now() - timedelta(days=days)
