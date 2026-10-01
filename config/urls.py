from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import admin_login
from apps.core import health

# Django admin signs in through the product's own view: lockout, rate limit and TOTP MFA (SEC-01).
admin.site.login = admin_login

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

# Development only: runserver serves uploaded photos from MEDIA_ROOT (static() is a no-op with
# DEBUG off). Production stores them in a private bucket and links pre-signed URLs instead.
if settings.DEBUG and not settings.USE_S3:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "apps.core.errors_views.forbidden"
handler404 = "apps.core.errors_views.not_found"
handler500 = "apps.core.errors_views.server_error"
