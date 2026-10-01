"""
REST API v1 (DRF + drf-spectacular), mounted at /api/v1/.

Every endpoint requires an authenticated session; each app's api.py adds the
capability permission and scopes its queryset (RBAC enforced twice).
"""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts.api import MeView
from apps.analytics.api import UtilisationView
from apps.approvals.api import ApprovalQueueViewSet
from apps.bookings.api import BookingViewSet, SeriesViewSet
from apps.catalogue.api import ResourceViewSet
from apps.maintenance.api import MaintenanceViewSet, ReportBreakdownView
from apps.notifications.api import NotificationViewSet
from apps.timetable.api import PublicationViewSet

router = DefaultRouter()
router.include_root_view = False
router.register("resources", ResourceViewSet, basename="resource")
router.register("bookings", BookingViewSet, basename="booking")
router.register("series", SeriesViewSet, basename="series")
router.register("approvals", ApprovalQueueViewSet, basename="approval")
router.register("maintenance", MaintenanceViewSet, basename="maintenance")
router.register("timetable/publications", PublicationViewSet, basename="timetable-publication")
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("me/", MeView.as_view(), name="api-me"),
    path("analytics/utilisation/", UtilisationView.as_view(), name="api-analytics-utilisation"),
    path("resources/<str:id_or_slug>/report-breakdown/", ReportBreakdownView.as_view(), name="api-report-breakdown"),
    *router.urls,
]
