from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views import CsrfView, CurrentUserView, LoginView, LogoutView, RegisterView
from core.views import SystemInfoView, liveness, readiness
from incidents.views import IncidentDetailView, IncidentListCreateView

urlpatterns = [
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
    path("api/v1/openapi/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="openapi-schema")),
    path("django-admin/", admin.site.urls),
]
