"""Staff console entry points shared across modules (home, setup hub, ops, placeholders)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.accounts.permissions import has_cap

STAFF_CAPS = ("approve_bookings", "manage_resources", "manage_maintenance", "manage_inventory",
              "view_department_analytics", "configure_policy", "manage_timetable", "manage_users")


def staff_required(*caps):
    """Decorator: login + at least one of the capabilities (server-side, not just hidden links)."""
    caps = caps or STAFF_CAPS

    def wrap(view):
        @login_required
        def inner(request, *args, **kwargs):
            if not any(has_cap(request.user, c) for c in caps):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        inner.__name__ = view.__name__
        inner.__doc__ = view.__doc__
        return inner

    return wrap


@staff_required()
def placeholder(request, *args, **kwargs):
    return render(request, "manage/placeholder.html", {"path": request.path})
