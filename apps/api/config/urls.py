from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.views import SystemInfoView, liveness, readiness

urlpatterns = [
    path("health/live", liveness, name="health-live"),
    path("health/ready", readiness, name="health-ready"),
    path("api/v1/system", SystemInfoView.as_view(), name="system-info"),
    path("api/v1/openapi/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="openapi-schema")),
    path("django-admin/", admin.site.urls),
]
