"""The staff console (/manage/): one URL namespace; each module owns its views."""

from django.urls import path

from apps.accounts import manage_views as users
from apps.approvals import manage_views as approvals
from apps.approvals import workflow_views as workflows
from apps.audit import manage_views as audit
from apps.bookings import manage_views as board
from apps.catalogue import manage_views as resources
from apps.catalogue import setup_views as catalogue
from apps.checkins import manage_views as no_shows
from apps.core import manage_home, manage_ops
from apps.inventory import manage_views as inventory
from apps.maintenance import manage_views as maintenance
from apps.rules import manage_views as rules
from apps.timetable import manage_views as timetable

app_name = "manage"

urlpatterns = [
    # Operations
    path("", manage_home.home, name="home"),
    path("approvals/", approvals.queue, name="approvals"),
    path("approvals/<int:pk>/decide/", approvals.decide, name="approval_decide"),
    path("board/", board.board, name="board"),
    path("no-shows/", no_shows.no_shows, name="no_shows"),
    path("no-shows/<int:pk>/forgive/", no_shows.forgive, name="no_show_forgive"),
    path("restrictions/<int:pk>/lift/", no_shows.lift, name="restriction_lift"),
    path("maintenance/", maintenance.index, name="maintenance"),
    path("maintenance/schedule/", maintenance.schedule, name="maintenance_schedule"),
    path("maintenance/windows/<int:pk>/<str:action>/", maintenance.window_action, name="maintenance_window"),
    path("maintenance/reports/<int:pk>/<str:action>/", maintenance.report_action, name="maintenance_report"),
    path("inventory/", inventory.index, name="inventory"),
    path("inventory/<int:pk>/restock/", inventory.restock, name="inventory_restock"),
    # Configuration
    path("resources/", resources.resources, name="resources"),
    path("resources/new/", resources.resource_new, name="resource_new"),
    path("resources/<int:pk>/", resources.resource_edit, name="resource_edit"),
    path("resources/<int:pk>/door-qr/", resources.door_qr, name="door_qr"),
    path("setup/", rules.setup, name="setup"),
    path("catalogue/", catalogue.catalogue, name="catalogue"),
    path("policies/", rules.policies, name="policies"),
    path("workflows/", workflows.workflows, name="workflows"),
    path("timetable/", timetable.timetable, name="timetable"),
    path("users/", users.users, name="users"),
    path("users/new/", users.user_new, name="user_new"),
    path("audit/", audit.audit, name="audit"),
    path("ops/", manage_ops.ops, name="ops"),
]
