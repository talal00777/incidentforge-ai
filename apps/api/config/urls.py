from django.conf import settings
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
from incidents.dashboard_views import DashboardSummaryView, DemoScenarioListCreateView
from incidents.views import IncidentDetailView, IncidentListCreateView
from incidents.warroom_views import (
    IncidentActionItemDetailView,
    IncidentActionItemsView,
    IncidentTimelineDetailView,
    IncidentTimelineView,
)
from ingestion.views import (
    EventContextView,
    EventFacetsView,
    EventsView,
    JobsView,
    SourcesView,
    UploadView,
)
from investigations.async_views import AIJobCancelView, AIJobDetailView, AIJobListCreateView
from investigations.postmortem_export_views import PostmortemDownloadView
from investigations.postmortem_views import PostmortemDetailView, PostmortemListCreateView
from investigations.review_views import InvestigationReviewView
from investigations.views import (
    InvestigationDetailView,
    InvestigationListCreateView,
    ProviderListView,
)
from workspaces.views import (
    WorkspaceDetailView,
    WorkspaceListCreateView,
    WorkspaceMemberDetailView,
    WorkspaceMembersView,
    WorkspaceWebhookDeliveriesView,
    WorkspaceWebhookDetailView,
    WorkspaceWebhooksView,
    WorkspaceWebhookTestView,
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
    path("api/v1/dashboard/summary", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("api/v1/demo/scenarios", DemoScenarioListCreateView.as_view(), name="demo-scenarios"),
    path("api/v1/workspaces", WorkspaceListCreateView.as_view(), name="workspace-list"),
    path(
        "api/v1/workspaces/<uuid:workspace_id>",
        WorkspaceDetailView.as_view(),
        name="workspace-detail",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/members",
        WorkspaceMembersView.as_view(),
        name="workspace-members",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/members/<uuid:membership_id>",
        WorkspaceMemberDetailView.as_view(),
        name="workspace-member-detail",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/webhooks",
        WorkspaceWebhooksView.as_view(),
        name="workspace-webhooks",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/webhooks/<uuid:webhook_id>",
        WorkspaceWebhookDetailView.as_view(),
        name="workspace-webhook-detail",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/webhooks/<uuid:webhook_id>/test",
        WorkspaceWebhookTestView.as_view(),
        name="workspace-webhook-test",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/webhooks/<uuid:webhook_id>/deliveries",
        WorkspaceWebhookDeliveriesView.as_view(),
        name="workspace-webhook-deliveries",
    ),
    path("api/v1/incidents", IncidentListCreateView.as_view(), name="incident-list"),
    path("api/v1/incidents/<uuid:id>", IncidentDetailView.as_view(), name="incident-detail"),
    path(
        "api/v1/incidents/<uuid:incident_id>/timeline",
        IncidentTimelineView.as_view(),
        name="incident-timeline",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/timeline/<uuid:entry_id>",
        IncidentTimelineDetailView.as_view(),
        name="incident-timeline-detail",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/action-items",
        IncidentActionItemsView.as_view(),
        name="incident-action-items",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/action-items/<uuid:item_id>",
        IncidentActionItemDetailView.as_view(),
        name="incident-action-item-detail",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/uploads", UploadView.as_view(), name="ingestion-upload"
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/sources",
        SourcesView.as_view(),
        name="ingestion-sources",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/events/facets",
        EventFacetsView.as_view(),
        name="ingestion-event-facets",
    ),
    path(
        "api/v1/incidents/<uuid:incident_id>/events/<uuid:event_id>/context",
        EventContextView.as_view(),
        name="ingestion-event-context",
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
]

if settings.ENABLE_DJANGO_ADMIN:
    urlpatterns.append(path("django-admin/", admin.site.urls))
