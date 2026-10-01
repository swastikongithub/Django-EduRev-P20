"""Staff console: the Setup hub, and the policies screen (booking rules, hours, blackouts, quotas, ladder)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Role, User
from apps.accounts.permissions import has_cap, is_campus_wide
from apps.audit.services import record, snapshot
from apps.catalogue.models import Resource, ResourceStatus, ResourceType
from apps.core.manage_views import staff_required

from .manage_forms import (
    BlackoutForm,
    BookingPolicyForm,
    HoursForm,
    QuotaForm,
    RestrictionTierForm,
    describe_blackout,
    describe_policy,
    describe_quota,
    describe_tier,
    scope_phrase,
    week_rows,
)
from .models import AvailabilityRule, Blackout, BookingPolicy, Quota, RestrictionTier, Scope
from .services import DEFAULT_HOURS, period_window

# ── Setup hub ───────────────────────────────────────────────────────────────

SETUP_CAPS = ("configure_policy", "manage_timetable", "manage_users", "view_audit_log")


def _ago(dt, now):
    if not dt:
        return ""
    days = (timezone.localdate(now) - timezone.localdate(dt)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def _plural(n, word, plural=None):
    return f"{n:,} {word if n == 1 else (plural or word + 's')}"


def hub_cards(user, now=None) -> list[dict]:
    """The cards this person's capabilities allow, each with a one-line live status."""
    now = now or timezone.now()
    inst = user.institution_id
    cards = []
    campus = is_campus_wide(user)

    if has_cap(user, "manage_resources") and campus:
        agg = Resource.objects.filter(institution_id=inst).aggregate(
            n=Count("id"), out=Count("id", filter=Q(status=ResourceStatus.OUT_OF_SERVICE))
        )
        status = _plural(agg["n"], "resource") + (
            f", {agg['out']} out of service" if agg["out"] else ", all in service"
        )
        cards.append(
            {
                "title": "Resources",
                "icon": "building-2",
                "url": reverse("manage:resources"),
                "status": status,
                "tone": "warn" if agg["out"] else "ok",
                "text": "Add rooms, labs and equipment, import a block from CSV, print door QR signs.",
            }
        )

    if has_cap(user, "configure_policy"):
        n_pol = BookingPolicy.objects.filter(institution_id=inst).count()
        n_black = Blackout.objects.filter(institution_id=inst, period__endswith__gte=now).count()
        n_quota = Quota.objects.filter(institution_id=inst, active=True).count()
        cards.append(
            {
                "title": "Booking rules",
                "icon": "sliders-horizontal",
                "url": reverse("manage:policies"),
                "status": f"{_plural(n_pol, 'policy', 'policies')}, {_plural(n_black, 'upcoming blackout')}, "
                f"{_plural(n_quota, 'active quota')}",
                "tone": "ok",
                "text": "Durations, notice, opening hours, blackouts, quotas and the no-show ladder."
                if campus
                else "Your department's shared quotas, and the campus rules that apply to it.",
            }
        )
        from apps.approvals.models import ApprovalWorkflow

        n_wf = ApprovalWorkflow.objects.filter(institution_id=inst, active=True).count()
        cards.append(
            {
                "title": "Approval workflows",
                "icon": "list-checks",
                "url": reverse("manage:workflows"),
                "status": f"{_plural(n_wf, 'workflow')} active",
                "tone": "ok" if n_wf else "warn",
                "text": "Who approves what, per resource type, with a tester to check any request.",
            }
        )

    if has_cap(user, "manage_timetable"):
        from apps.timetable.models import PublicationStatus, TimetablePublication

        pub = (
            TimetablePublication.objects.filter(institution_id=inst, status=PublicationStatus.PUBLISHED)
            .select_related("term")
            .order_by("-published_at")
            .first()
        )
        drafts = TimetablePublication.objects.filter(institution_id=inst, status=PublicationStatus.DRAFT).count()
        if pub:
            status = f"{pub.term.name} v{pub.version} published {_ago(pub.published_at, now)}"
        else:
            status = "No timetable published yet"
        if drafts:
            status += f", {_plural(drafts, 'draft')} waiting"
        cards.append(
            {
                "title": "Timetable",
                "icon": "calendar-days",
                "url": reverse("manage:timetable"),
                "status": status,
                "tone": "ok" if pub and not drafts else "warn",
                "text": "Upload the term timetable. Classes become hard blocks in every room's availability.",
            }
        )

    if has_cap(user, "manage_users") or campus:
        agg = User.objects.filter(institution_id=inst).aggregate(
            n=Count("id", filter=Q(is_active=True)),
            off=Count("id", filter=Q(is_active=False)),
            staff=Count("id", filter=Q(is_active=True) & ~Q(role__in=[Role.STUDENT, Role.FACULTY, Role.STAFF])),
        )
        cards.append(
            {
                "title": "Users and roles",
                "icon": "users",
                "url": reverse("manage:users"),
                "status": f"{_plural(agg['n'], 'active account')}, {agg['staff']} with console roles",
                "tone": "ok",
                "text": "Change roles and deactivate accounts."
                if has_cap(user, "manage_users")
                else "See who holds which role. Administrators make changes.",
            }
        )

    if has_cap(user, "forgive_no_shows") and campus:
        from apps.checkins.models import Restriction

        n = Restriction.objects.filter(
            institution_id=inst, starts_at__lte=now, ends_at__gt=now, lifted_at__isnull=True
        ).count()
        cards.append(
            {
                "title": "No-shows",
                "icon": "ban",
                "url": reverse("manage:no_shows"),
                "status": f"{_plural(n, 'person', 'people')} paused from booking right now",
                "tone": "warn" if n else "ok",
                "text": "Forgive mistaken no-shows and lift booking pauses.",
            }
        )

    if has_cap(user, "view_audit_log"):
        from apps.audit.models import AuditLog

        n = AuditLog.objects.filter(institution_id=inst, created_at__gte=now - timedelta(days=1)).count()
        cards.append(
            {
                "title": "Audit log",
                "icon": "history",
                "url": reverse("manage:audit"),
                "status": f"{_plural(n, 'recorded action')} in the last 24 hours",
                "tone": "ok",
                "text": "Every privileged change: who, what, before and after. It can't be edited.",
            }
        )

    if campus:
        from apps.core.manage_ops import sweep_status

        rows = sweep_status(now)
        stalled = [r for r in rows if r["stalled"] or r["failed"]]
        status = (
            f"{_plural(len(stalled), 'background job')} need{'s' if len(stalled) == 1 else ''} attention"
            if stalled
            else f"All {len(rows)} background jobs on schedule"
        )
        cards.append(
            {
                "title": "Operations",
                "icon": "gauge",
                "url": reverse("manage:ops"),
                "status": status,
                "tone": "warn" if stalled else "ok",
                "text": "Database and Redis health, background sweeps, and Run now for demos.",
            }
        )
    return cards


@staff_required(*SETUP_CAPS)
def setup(request):
    return render(request, "manage/setup.html", {"cards": hub_cards(request.user)})


# ── Policies ────────────────────────────────────────────────────────────────

TABS = [
    ("booking", "Booking rules", "timer"),
    ("hours", "Opening hours", "clock"),
    ("blackouts", "Blackouts", "ban"),
    ("quotas", "Quotas", "gauge"),
    ("ladder", "No-show ladder", "shield-check"),
]
TAB_KEYS = {t[0] for t in TABS}
WEEK_HOURS = list(range(6, 24, 3))


def _back(tab):
    return redirect(f"{reverse('manage:policies')}?tab={tab}")


def _require_campus(request):
    if not is_campus_wide(request.user):
        raise PermissionDenied("Campus-wide rules are set by facility managers and administrators.")


def _quota_scope(user):
    qs = Quota.objects.filter(institution_id=user.institution_id)
    if is_campus_wide(user):
        return qs
    return qs.filter(department_id=user.department_id, department__isnull=False)


def _audit(request, action, obj, before=None, after=None, label=None):
    record(request.user, action, obj, before=before, after=after, request=request, label=label)


def _get(model, request, pk):
    return get_object_or_404(model, institution_id=request.user.institution_id, pk=pk)


# Each POST action returns either a redirect, or a context dict with the bound form to re-show.


def _save_model(request, *, model, form_cls, tab, noun, action_prefix, form_kwargs, describe, instance_qs=None):
    pk = request.POST.get("pk")
    if pk:
        instance = get_object_or_404(
            instance_qs
            if instance_qs is not None
            else model.objects.filter(institution_id=request.user.institution_id),
            pk=pk,
        )
        before = snapshot(instance)
    else:
        instance, before = model(institution_id=request.user.institution_id), None
    form = form_cls(request.POST, instance=instance, **form_kwargs)
    if not form.is_valid():
        return {"form": form, "editing": bool(pk)}
    obj = form.save(commit=False)
    obj.institution_id = request.user.institution_id
    obj.save()
    if hasattr(form, "save_m2m"):
        form.save_m2m()
    _audit(request, f"{action_prefix}.{'update' if before else 'create'}", obj, before=before, after=snapshot(obj))
    messages.success(
        request, f"{noun} {'saved' if before else 'added'}. {describe(obj)} It applies from the next booking."
    )
    return _back(tab)


def _delete_model(request, *, qs, tab, noun, action_prefix, label=None):
    obj = get_object_or_404(qs, pk=request.POST.get("pk"))
    before = snapshot(obj)
    lbl = label(obj) if label else str(obj)
    _audit(request, f"{action_prefix}.delete", obj, before=before, label=lbl)
    obj.delete()
    messages.success(request, f"{noun} removed. It no longer applies to new bookings.")
    return _back(tab)


def act_policy_save(request):
    _require_campus(request)
    return _save_model(
        request,
        model=BookingPolicy,
        form_cls=BookingPolicyForm,
        tab="booking",
        noun="Booking rule",
        action_prefix="rules.policy",
        form_kwargs={"institution_id": request.user.institution_id},
        describe=lambda p: f"{scope_phrase(p)[:1].upper()}{scope_phrase(p)[1:]}: {describe_policy(p)}",
    )


def act_policy_delete(request):
    _require_campus(request)
    return _delete_model(
        request,
        qs=BookingPolicy.objects.filter(institution_id=request.user.institution_id),
        tab="booking",
        noun="Booking rule",
        action_prefix="rules.policy",
        label=lambda p: f"Policy for {scope_phrase(p)}",
    )


def act_hours_add(request):
    _require_campus(request)
    form = HoursForm(request.POST, institution_id=request.user.institution_id)
    if not form.is_valid():
        return {"form": form, "editing": False}
    rules = form.save()
    for r in rules:
        _audit(request, "rules.hours.add", r, after=snapshot(r), label=f"{r} for {scope_phrase(r)}")
    first = rules[0]
    messages.success(
        request,
        f"Opening hours added for {scope_phrase(first)}: "
        f"{', '.join(r.get_weekday_display()[:3] for r in rules)} {first.opens:%H:%M}–{first.closes:%H:%M}.",
    )
    return _back("hours")


def act_hours_remove(request):
    _require_campus(request)
    rule = _get(AvailabilityRule, request, request.POST.get("pk"))
    left = (
        AvailabilityRule.objects.filter(
            institution_id=rule.institution_id,
            scope=rule.scope,
            resource_type_id=rule.resource_type_id,
            resource_id=rule.resource_id,
        )
        .exclude(pk=rule.pk)
        .count()
    )
    _audit(request, "rules.hours.remove", rule, before=snapshot(rule), label=f"{rule} for {scope_phrase(rule)}")
    rule.delete()
    tail = (
        ""
        if left
        else (
            " That was the last interval here, so the next broader hours apply"
            " (type, then campus, then Mon–Sat 08:00–20:00)."
        )
    )
    messages.success(request, f"Removed {rule} for {scope_phrase(rule)}.{tail}")
    return _back("hours")


def act_blackout_save(request):
    _require_campus(request)
    return _save_model(
        request,
        model=Blackout,
        form_cls=BlackoutForm,
        tab="blackouts",
        noun="Blackout",
        action_prefix="rules.blackout",
        form_kwargs={"institution_id": request.user.institution_id},
        describe=describe_blackout,
    )


def act_blackout_delete(request):
    _require_campus(request)
    return _delete_model(
        request,
        qs=Blackout.objects.filter(institution_id=request.user.institution_id),
        tab="blackouts",
        noun="Blackout",
        action_prefix="rules.blackout",
    )


def act_quota_save(request):
    return _save_model(
        request,
        model=Quota,
        form_cls=QuotaForm,
        tab="quotas",
        noun="Quota",
        action_prefix="rules.quota",
        form_kwargs={"user": request.user},
        describe=describe_quota,
        instance_qs=_quota_scope(request.user),
    )


def act_quota_delete(request):
    return _delete_model(
        request, qs=_quota_scope(request.user), tab="quotas", noun="Quota", action_prefix="rules.quota"
    )


def act_quota_toggle(request):
    q = get_object_or_404(_quota_scope(request.user), pk=request.POST.get("pk"))
    before = snapshot(q)
    q.active = not q.active
    q.save(update_fields=["active", "updated_at"])
    _audit(request, f"rules.quota.{'activate' if q.active else 'deactivate'}", q, before=before, after=snapshot(q))
    messages.success(
        request,
        f"{q.name} is {'on: it counts from the next booking' if q.active else 'off: nobody is limited by it now'}.",
    )
    return _back("quotas")


def act_tier_save(request):
    _require_campus(request)
    return _save_model(
        request,
        model=RestrictionTier,
        form_cls=RestrictionTierForm,
        tab="ladder",
        noun="Ladder step",
        action_prefix="rules.tier",
        form_kwargs={"institution_id": request.user.institution_id},
        describe=describe_tier,
    )


def act_tier_delete(request):
    _require_campus(request)
    return _delete_model(
        request,
        qs=RestrictionTier.objects.filter(institution_id=request.user.institution_id),
        tab="ladder",
        noun="Ladder step",
        action_prefix="rules.tier",
    )


ACTIONS = {
    "policy.save": ("booking", act_policy_save),
    "policy.delete": ("booking", act_policy_delete),
    "hours.add": ("hours", act_hours_add),
    "hours.remove": ("hours", act_hours_remove),
    "blackout.save": ("blackouts", act_blackout_save),
    "blackout.delete": ("blackouts", act_blackout_delete),
    "quota.save": ("quotas", act_quota_save),
    "quota.delete": ("quotas", act_quota_delete),
    "quota.toggle": ("quotas", act_quota_toggle),
    "tier.save": ("ladder", act_tier_save),
    "tier.delete": ("ladder", act_tier_delete),
}


@staff_required("configure_policy")
@require_http_methods(["GET", "POST"])
def policies(request):
    user = request.user
    campus = is_campus_wide(user)
    bound = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action not in ACTIONS:
            return HttpResponseBadRequest("Unknown action")
        tab, handler = ACTIONS[action]
        result = handler(request)
        if not isinstance(result, dict):
            return result
        bound = result
    else:
        tab = request.GET.get("tab", "")
        if tab not in TAB_KEYS:
            tab = "booking" if campus else "quotas"

    ctx = {
        "tab": tab,
        "tabs": TABS,
        "campus": campus,
        "can_edit": campus or tab == "quotas",
        "bound": bound,
        "now": timezone.now(),
    }
    ctx.update(BUILDERS[tab](request, bound))
    if not campus and not user.department_id and tab == "quotas":
        ctx["can_edit"] = False
    return render(request, "manage/policies.html", ctx)


def _edit_instance(request, qs):
    pk = request.GET.get("edit")
    if pk and pk.isdigit():
        return qs.filter(pk=pk).first()
    return None


def _forms(request, bound, form_cls, qs, **kw):
    """(new_form, edit_form, autoopen) — a bound form with errors goes back into the sheet it came from."""
    new_form = form_cls(**kw)
    edit_form, autoopen = None, ""
    if bound:
        if bound["editing"]:
            edit_form, autoopen = bound["form"], "edit-sheet"
        else:
            new_form, autoopen = bound["form"], "new-sheet"
    else:
        inst = _edit_instance(request, qs)
        if inst:
            edit_form, autoopen = form_cls(instance=inst, **kw), "edit-sheet"
    return new_form, edit_form, autoopen


def build_booking(request, bound):
    inst = request.user.institution_id
    qs = BookingPolicy.objects.filter(institution_id=inst).select_related("resource_type", "resource")
    kw = {"institution_id": inst}
    new_form, edit_form, autoopen = _forms(request, bound, BookingPolicyForm, qs, **kw)
    target = request.GET.get("resource")
    if not bound and target and target.isdigit():
        existing = qs.filter(scope=Scope.RESOURCE, resource_id=target).first()
        if existing:
            edit_form, autoopen = BookingPolicyForm(instance=existing, **kw), "edit-sheet"
        elif Resource.objects.filter(institution_id=inst, pk=target).exists():
            new_form = BookingPolicyForm(initial={"scope": Scope.RESOURCE, "resource": target}, **kw)
            autoopen = "new-sheet"
    rows = list(qs)
    for p in rows:
        p.summary = describe_policy(p)
        p.target = scope_phrase(p)
    campus_row = next((p for p in rows if p.scope == Scope.CAMPUS), None)
    by_type = {p.resource_type_id: p for p in rows if p.scope == Scope.TYPE}
    types = list(ResourceType.objects.filter(institution_id=inst).annotate(n=Count("resources")))
    for t in types:
        t.policy = by_type.get(t.pk)
    return {
        "campus_policy": campus_row,
        "types": types,
        "resource_policies": [p for p in rows if p.scope == Scope.RESOURCE],
        "new_form": new_form,
        "edit_form": edit_form,
        "autoopen": autoopen,
    }


def build_hours(request, bound):
    inst = request.user.institution_id
    rules = list(AvailabilityRule.objects.filter(institution_id=inst).select_related("resource_type", "resource"))
    groups = {}
    for r in rules:
        groups.setdefault((r.scope, r.resource_type_id, r.resource_id), []).append(r)
    campus_rules = groups.get((Scope.CAMPUS, None, None))
    types = list(ResourceType.objects.filter(institution_id=inst))
    blocks = [
        {
            "title": "Whole campus",
            "note": "Used by any type without its own hours.",
            "rows": week_rows(campus_rules) if campus_rules else None,
            "scope": Scope.CAMPUS,
            "target": "",
        }
    ]
    if not campus_rules:
        blocks[0]["fallback"] = "Not set, so the built-in Mon–Sat 08:00–20:00 applies."
        blocks[0]["fallback_rows"] = week_rows(_default_rules())
    for t in types:
        own = groups.get((Scope.TYPE, t.pk, None))
        blocks.append(
            {
                "title": t.plural or t.name,
                "rows": week_rows(own) if own else None,
                "scope": Scope.TYPE,
                "target": t.pk,
                "fallback": None if own else "Uses the campus hours.",
            }
        )
    for (scope, _t, rid), rs in groups.items():
        if scope == Scope.RESOURCE:
            blocks.append(
                {
                    "title": rs[0].resource.name,
                    "note": "Override for one resource.",
                    "rows": week_rows(rs),
                    "scope": Scope.RESOURCE,
                    "target": rid,
                }
            )
    form = bound["form"] if bound else HoursForm(institution_id=inst, initial={"weekdays": [0, 1, 2, 3, 4, 5]})
    return {
        "blocks": blocks,
        "hour_ticks": [{"h": h, "left": (h - 6) / 17 * 100} for h in WEEK_HOURS],
        "new_form": form,
        "autoopen": "new-sheet" if bound else "",
    }


def _default_rules():
    return [AvailabilityRule(weekday=wd, opens=o, closes=c) for wd, spans in DEFAULT_HOURS.items() for o, c in spans]


def build_blackouts(request, bound):
    inst = request.user.institution_id
    now = timezone.now()
    qs = Blackout.objects.filter(institution_id=inst).select_related("resource_type", "resource", "building")
    kw = {"institution_id": inst}
    new_form, edit_form, autoopen = _forms(request, bound, BlackoutForm, qs, **kw)
    upcoming = list(qs.filter(period__endswith__gte=now).order_by("period"))
    past = list(qs.filter(period__endswith__lt=now).order_by("-period")[:12])
    for b in upcoming + past:
        b.summary = describe_blackout(b)
        b.start, b.end = b.period.lower, b.period.upper
        b.live = b.start <= now < b.end
    return {"upcoming": upcoming, "past": past, "new_form": new_form, "edit_form": edit_form, "autoopen": autoopen}


def build_quotas(request, bound):
    from apps.bookings.services import consumption

    user = request.user
    now = timezone.now()
    qs = _quota_scope(user).select_related("department", "resource_type")
    new_form, edit_form, autoopen = _forms(request, bound, QuotaForm, qs, user=user)
    role_counts = dict(
        User.objects.filter(institution_id=user.institution_id, is_active=True)
        .values_list("role")
        .annotate(n=Count("id"))
    )
    quotas = list(qs.order_by("-active", "name"))
    for q in quotas:
        q.summary = describe_quota(q)
        if q.department_id:
            window = period_window(q.period, now)
            minutes, count = consumption(
                window=window, department_id=q.department_id, resource_type_id=q.resource_type_id
            )
            q.hours_used = round(minutes / 60, 1)
            q.bookings_used = count
            pcts = []
            if q.max_hours:
                pcts.append(min(100, int(q.hours_used / float(q.max_hours) * 100)))
            if q.max_bookings:
                pcts.append(min(100, int(count * 100 / q.max_bookings)))
            q.pct = max(pcts or [0])
        else:
            q.people = role_counts.get(q.role, 0)
    return {
        "quotas": quotas,
        "new_form": new_form,
        "edit_form": edit_form,
        "autoopen": autoopen,
        "department": user.department if not is_campus_wide(user) else None,
    }


def build_ladder(request, bound):
    inst = request.user.institution_id
    qs = RestrictionTier.objects.filter(institution_id=inst)
    new_form, edit_form, autoopen = _forms(request, bound, RestrictionTierForm, qs, institution_id=inst)
    tiers = list(qs)
    for t in tiers:
        t.summary = describe_tier(t)
    return {"tiers": tiers, "new_form": new_form, "edit_form": edit_form, "autoopen": autoopen}


BUILDERS = {
    "booking": build_booking,
    "hours": build_hours,
    "blackouts": build_blackouts,
    "quotas": build_quotas,
    "ladder": build_ladder,
}
