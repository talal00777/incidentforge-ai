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
from investigations.async_views import AIJobCancelView, AIJobDetailView, AIJobListCreateView
from investigations.postmortem_export_views import PostmortemDownloadView
from investigations.postmortem_views import PostmortemDetailView, PostmortemListCreateView
from investigations.review_views import InvestigationReviewView
from investigations.views import (
    InvestigationDetailView,
    InvestigationListCreateView,
    ProviderListView,
)

urlpatterns = [
    path(
        "api/v1/incidents/<uuid:incident_id>/ai-runs",
        AIJobListCreateView.as_view(),
        name="ai-job-list",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/ai-runs/<uuid:job_id>",
        AIJobDetailView.as_view(),
        name="ai-job-detail",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/ai-runs/<uuid:job_id>/cancel",
        AIJobCancelView.as_view(),
        name="ai-job-cancel",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/reports/<uuid:version_id>/download",
        PostmortemDownloadView.as_view(),
        name="postmortem-download",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/reports",
        PostmortemListCreateView.as_view(),
        name="postmortem-list",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/reports/<uuid:version_id>",
        PostmortemDetailView.as_view(),
        name="postmortem-detail",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/investigations/<uuid:report_id>/review",
        InvestigationReviewView.as_view(),
        name="investigation-review",
    ),
    path(
        "api/v1/investigation/providers", ProviderListView.as_view(), name="investigation-providers"
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/investigations",
        InvestigationListCreateView.as_view(),
        name="investigation-list",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/investigations/<uuid:report_id>",
        InvestigationDetailView.as_view(),
        name="investigation-detail",
    ),
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
