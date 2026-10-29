from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views import CsrfView, CurrentUserView, LoginView, LogoutView, RegisterView
from analytics.charts import IncidentChartView
from analytics.correlation_views import IncidentRelationshipsView
from analytics.views import IncidentAnalysisView
from core.views import SystemInfoView, liveness, readiness
from evidence.views import (
    EvidencePreviewView,
    EvidenceSnapshotDetailView,
    EvidenceSnapshotListCreateView,
)
from incidents.views import IncidentDetailView, IncidentListCreateView
from ingestion.views import EventsView, JobsView, SourcesView, UploadView

urlpatterns = [
    path(
        "api/v1/incidents/<uuid:incident_id>/evidence/preview",
        EvidencePreviewView.as_view(),
        name="evidence-preview",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/evidence/snapshots",
        EvidenceSnapshotListCreateView.as_view(),
        name="evidence-snapshots",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/evidence/snapshots/<uuid:snapshot_id>",
        EvidenceSnapshotDetailView.as_view(),
        name="evidence-snapshot",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/relationships",
        IncidentRelationshipsView.as_view(),
        name="incident-relationships",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/analysis/charts/<slug:chart_type>",
        IncidentChartView.as_view(),
        name="incident-chart",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/analysis",
        IncidentAnalysisView.as_view(),
        name="incident-analysis",
    ),
    path("health/live", liveness, name="health-live"),
    path("health/ready", readiness, name="health-ready"),
    path("api/v1/system", SystemInfoView.as_view(), name="system-info"),
    path("api/v1/auth/csrf", CsrfView.as_view(), name="auth-csrf"),
    path("api/v1/auth/register", RegisterView.as_view(), name="auth-register"),
    path("api/v1/auth/login", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/auth/me", CurrentUserView.as_view(), name="auth-me"),
    path("api/v1/incidents", IncidentListCreateView.as_view(), name="incident-list"),
    path("api/v1/incidents/<uuid:id>", IncidentDetailView.as_view(), name="incident-detail"),
    path(
        "api/v1/incidents/<uuid:incident_id>/uploads", UploadView.as_view(), name="ingestion-upload"
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/sources",
        SourcesView.as_view(),
        name="ingestion-sources",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/events", EventsView.as_view(), name="ingestion-events"
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/jobs/<uuid:job_id>",
        JobsView.as_view(),
        name="ingestion-job",
    ),
    path("api/v1/openapi/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="openapi-schema")),
    path("django-admin/", admin.site.urls),
]
