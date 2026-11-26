"""Live owner-scoped operational dashboard aggregations."""

from statistics import median

from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from evidence.models import EvidenceSnapshot
from incidents.models import Incident, IncidentAuditEvent
from ingestion.models import LogEvent, LogSource
from investigations.models import InvestigationReport, PostmortemVersion
from workspaces.permissions import accessible_incidents_queryset

ERROR_SEVERITIES = ("ERROR", "FATAL", "CRITICAL")
SEVERITY_ORDER = (
    Incident.Severity.CRITICAL,
    Incident.Severity.HIGH,
    Incident.Severity.MEDIUM,
    Incident.Severity.LOW,
)
ACTIVE_STATUSES = (Incident.Status.OPEN, Incident.Status.INVESTIGATING)


def _count_subquery(model, filter_kwargs=None):
    qs = model.objects.filter(incident_id=OuterRef("pk"))
    if filter_kwargs:
        qs = qs.filter(**filter_kwargs)
    return Coalesce(
        Subquery(qs.values("incident_id").annotate(total=Count("id")).values("total")[:1]),
        Value(0),
    )


def build_dashboard_summary(user) -> dict:
    """Compute live operational telemetry strictly scoped to user's accessible incidents."""
    owned = accessible_incidents_queryset(user)

    counts_agg = owned.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Incident.Status.OPEN)),
        investigating=Count("id", filter=Q(status=Incident.Status.INVESTIGATING)),
        resolved=Count("id", filter=Q(status=Incident.Status.RESOLVED)),
        archived=Count("id", filter=Q(status=Incident.Status.ARCHIVED)),
        critical_open=Count(
            "id",
            filter=Q(severity=Incident.Severity.CRITICAL, status__in=ACTIVE_STATUSES),
        ),
        high_open=Count(
            "id",
            filter=Q(severity=Incident.Severity.HIGH, status__in=ACTIVE_STATUSES),
        ),
    )

    sev_rows = {
        row["severity"]: row
        for row in owned.values("severity").annotate(
            count=Count("id"),
            open_count=Count("id", filter=Q(status__in=ACTIVE_STATUSES)),
        )
    }
    severity_breakdown = [
        {
            "severity": sev,
            "count": sev_rows.get(sev, {}).get("count", 0),
            "open_count": sev_rows.get(sev, {}).get("open_count", 0),
        }
        for sev in SEVERITY_ORDER
    ]

    events_qs = LogEvent.objects.filter(incident__in=owned)
    events_agg = events_qs.aggregate(
        total_events=Count("id"),
        total_error_events=Count("id", filter=Q(severity__in=ERROR_SEVERITIES)),
    )
    telemetry_totals = {
        "total_sources": LogSource.objects.filter(incident__in=owned).count(),
        "total_events": events_agg["total_events"],
        "total_error_events": events_agg["total_error_events"],
        "total_snapshots": EvidenceSnapshot.objects.filter(incident__in=owned).count(),
        "total_investigations": InvestigationReport.objects.filter(incident__in=owned).count(),
        "total_postmortems": PostmortemVersion.objects.filter(incident__in=owned).count(),
    }

    resolved_durations = [
        max(0.0, (updated - created).total_seconds() / 60.0)
        for created, updated in owned.filter(status=Incident.Status.RESOLVED).values_list(
            "created_at", "updated_at"
        )
    ]
    mttr_minutes = round(float(median(resolved_durations)), 1) if resolved_durations else None

    service_rows = list(
        events_qs.exclude(service="")
        .values("service")
        .annotate(
            incident_count=Count("incident_id", distinct=True),
            event_count=Count("id"),
            error_events=Count("id", filter=Q(severity__in=ERROR_SEVERITIES)),
        )
        .order_by("-error_events", "-event_count", "service")[:6]
    )
    if not service_rows:
        service_rows = [
            {
                "service": row["service_name"],
                "incident_count": row["incident_count"],
                "event_count": 0,
                "error_events": 0,
            }
            for row in owned.exclude(service_name="")
            .values("service_name")
            .annotate(incident_count=Count("id"))
            .order_by("-incident_count", "service_name")[:6]
        ]

    recent_incidents = [
        {
            "id": str(item.id),
            "title": item.title,
            "service_name": item.service_name,
            "environment": item.environment,
            "severity": item.severity,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "source_count": item.source_count,
            "event_count": item.event_count,
            "error_count": item.error_count,
            "investigation_count": item.investigation_count,
            "postmortem_count": item.postmortem_count,
        }
        for item in owned.annotate(
            source_count=_count_subquery(LogSource),
            event_count=_count_subquery(LogEvent),
            error_count=_count_subquery(LogEvent, {"severity__in": ERROR_SEVERITIES}),
            investigation_count=_count_subquery(InvestigationReport),
            postmortem_count=_count_subquery(PostmortemVersion),
        ).order_by("-updated_at", "-id")[:8]
    ]

    activity: list[dict] = []
    for audit in IncidentAuditEvent.objects.filter(incident__in=owned).select_related("incident")[
        :8
    ]:
        verb = {
            IncidentAuditEvent.Action.CREATED: "Created incident",
            IncidentAuditEvent.Action.UPDATED: "Updated incident",
            IncidentAuditEvent.Action.DELETED: "Deleted incident",
        }.get(audit.action, "Updated incident")
        fields = f" ({', '.join(audit.changed_fields)})" if audit.changed_fields else ""
        activity.append(
            {
                "id": f"audit:{audit.id}",
                "kind": f"incident_{audit.action}",
                "summary": f"{verb}{fields}",
                "incident_id": str(audit.incident_id),
                "incident_title": audit.incident.title,
                "occurred_at": audit.occurred_at,
            }
        )

    for source in (
        LogSource.objects.filter(incident__in=owned, state=LogSource.State.COMPLETE)
        .select_related("incident")
        .order_by("-created_at")[:6]
    ):
        activity.append(
            {
                "id": f"source:{source.id}",
                "kind": "source_ingested",
                "summary": f"Ingested {source.filename} ({source.accepted} events)",
                "incident_id": str(source.incident_id),
                "incident_title": source.incident.title,
                "occurred_at": source.created_at,
            }
        )

    for report in (
        InvestigationReport.objects.filter(incident__in=owned)
        .select_related("incident")
        .order_by("-created_at")[:6]
    ):
        activity.append(
            {
                "id": f"report:{report.id}",
                "kind": "investigation_completed",
                "summary": f"Completed AI investigation ({report.provider} / {report.model_id})",
                "incident_id": str(report.incident_id),
                "incident_title": report.incident.title,
                "occurred_at": report.created_at,
            }
        )

    for pm in (
        PostmortemVersion.objects.filter(incident__in=owned)
        .select_related("incident")
        .order_by("-created_at")[:6]
    ):
        activity.append(
            {
                "id": f"postmortem:{pm.id}",
                "kind": "postmortem_finalized",
                "summary": f"Finalized postmortem Version {pm.version}",
                "incident_id": str(pm.incident_id),
                "incident_title": pm.incident.title,
                "occurred_at": pm.created_at,
            }
        )

    activity.sort(key=lambda item: item["occurred_at"], reverse=True)

    return {
        "counts": counts_agg,
        "severity_breakdown": severity_breakdown,
        "telemetry_totals": telemetry_totals,
        "mttr_minutes": mttr_minutes,
        "service_health": service_rows,
        "recent_incidents": recent_incidents,
        "recent_activity": activity[:12],
    }
