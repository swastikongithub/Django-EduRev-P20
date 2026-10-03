"""
The Setup checklist: what a new installation still needs before people can book.

Every step is read from the database on each request, so nothing is ever ticked by hand and a
step un-ticks itself if its last record goes. Steps that not every institution needs (departments,
blocks, approval workflows) are marked optional and never hold the checklist back. Each step links
to the existing screen that does the work, and only when this person may use that screen: the
links reflect the same capability checks those views enforce server-side.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import Department, Role, User
from apps.accounts.permissions import has_cap, is_campus_wide


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    text: str
    count: int
    noun: str
    optional: bool = False
    add_url: str | None = None
    add_label: str = ""
    view_url: str | None = None

    @property
    def done(self) -> bool:
        return self.count > 0

    @property
    def count_label(self) -> str:
        return f"{self.count:,} {self.noun if self.count == 1 else self.noun + 's'}"


def setup_checklist(user) -> dict | None:
    """The checklist for campus-wide staff (facility managers, administrators), else None."""
    if not is_campus_wide(user):
        return None
    from apps.approvals.models import ApprovalWorkflow
    from apps.catalogue.models import Building, Resource, ResourceStatus, ResourceType

    inst = user.institution_id
    catalogue = reverse("manage:catalogue")
    can_catalogue = has_cap(user, "manage_resources")
    can_people = has_cap(user, "manage_users")
    can_workflows = has_cap(user, "configure_policy")
    admins = Q(role=Role.ADMIN) | Q(is_superuser=True)
    people = User.objects.filter(institution_id=inst, is_active=True)

    steps = [
        Step(
            "admin",
            "Administrator account",
            "Someone who can add people and change roles.",
            people.filter(admins).count(),
            "administrator",
        ),
        Step(
            "department",
            "Department",
            "Needed for heads of department and department quotas, for example Computer Science and Engineering.",
            Department.objects.filter(institution_id=inst).count(),
            "department",
            optional=True,
            add_url=f"{catalogue}?tab=departments&new=1" if can_catalogue else None,
            add_label="Add a department",
            view_url=f"{catalogue}?tab=departments" if can_catalogue else None,
        ),
        Step(
            "block",
            "Block or building",
            "Where resources are, as signposted on campus. Resources can be added without one.",
            Building.objects.filter(institution_id=inst).count(),
            "block",
            optional=True,
            add_url=f"{catalogue}?tab=buildings&new=1" if can_catalogue else None,
            add_label="Add a block",
            view_url=f"{catalogue}?tab=buildings" if can_catalogue else None,
        ),
        Step(
            "type",
            "Resource type",
            "What kinds of thing can be booked, for example Classroom. Every resource has one.",
            ResourceType.objects.filter(institution_id=inst).count(),
            "resource type",
            add_url=f"{catalogue}?tab=types&new=1" if can_catalogue else None,
            add_label="Add a resource type",
            view_url=f"{catalogue}?tab=types" if can_catalogue else None,
        ),
        Step(
            "people",
            "People",
            "Students, faculty and staff who book, and the staff who approve. Administrators are not counted.",
            people.exclude(admins).count(),
            "account",
            add_url=reverse("manage:user_new") if can_people else None,
            add_label="Add a person",
            view_url=reverse("manage:users"),
        ),
        Step(
            "workflow",
            "Approval workflow",
            "Only if some bookings need someone's approval. Without one, bookings are confirmed instantly.",
            ApprovalWorkflow.objects.filter(institution_id=inst, active=True).count(),
            "active workflow",
            optional=True,
            add_url=f"{reverse('manage:workflows')}?new=1" if can_workflows else None,
            add_label="Add a workflow",
            view_url=reverse("manage:workflows") if can_workflows else None,
        ),
        Step(
            "resource",
            "First resource",
            "A room, lab, court or piece of equipment people can book.",
            Resource.objects.filter(institution_id=inst).exclude(status=ResourceStatus.RETIRED).count(),
            "resource",
            add_url=reverse("manage:resource_new") if can_catalogue else None,
            add_label="Add a resource",
            view_url=reverse("manage:resources") if can_catalogue else None,
        ),
    ]
    essential = [s for s in steps if not s.optional]
    return {
        "steps": steps,
        "done": sum(s.done for s in steps),
        "total": len(steps),
        "essential_left": sum(not s.done for s in essential),
        "ready": all(s.done for s in essential),
    }
