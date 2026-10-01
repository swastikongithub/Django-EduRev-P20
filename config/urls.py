from django.contrib import admin
from django.urls import include, path

from apps.core import health

urlpatterns = [
    path("health/", health.liveness, name="health"),
    path("ready/", health.readiness, name="ready"),
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
    path("", include("apps.catalogue.urls")),
    path("", include("apps.bookings.urls")),
]
