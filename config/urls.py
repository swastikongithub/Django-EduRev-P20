from django.contrib import admin
from django.urls import include, path

from apps.core import health

urlpatterns = [
    path("health/", health.liveness, name="health"),
    path("ready/", health.readiness, name="ready"),
    path("django-admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include("config.api_urls")),
    path("manage/", include("config.manage_urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.catalogue.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.checkins.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.maintenance.urls")),
    path("", include("apps.analytics.urls")),
]

handler403 = "apps.core.errors_views.forbidden"
handler404 = "apps.core.errors_views.not_found"
handler500 = "apps.core.errors_views.server_error"
