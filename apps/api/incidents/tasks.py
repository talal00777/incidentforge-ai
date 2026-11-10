from io import StringIO

from celery import shared_task
from django.conf import settings
from django.core.management import call_command


@shared_task
def purge_deleted_reports():
    if not settings.RETENTION_CLEANUP_ENABLED:
        return "disabled"
    call_command(
        "purge_deleted_incident_reports",
        "--execute",
        minimum_deleted_days=settings.RETENTION_REPORT_DAYS,
        max_incidents=25,
        stdout=StringIO(),
    )
    return "complete"


@shared_task
def purge_deleted_evidence():
    if not settings.RETENTION_CLEANUP_ENABLED:
        return "disabled"
    call_command(
        "purge_deleted_incident_evidence",
        "--execute",
        minimum_deleted_days=settings.RETENTION_EVIDENCE_DAYS,
        max_incidents=25,
        stdout=StringIO(),
    )
    return "complete"
