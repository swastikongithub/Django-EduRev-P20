"""
Policy console forms and the plain-English sentences that describe each rule.

Scope is always most-specific-wins (resource > type > campus); these forms keep each
row consistent with that model and refuse rules that would silently shadow another.
"""

from __future__ import annotations

from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department, Role
from apps.catalogue.manage_forms import StyledFormMixin
from apps.catalogue.models import Building, Resource, ResourceType
from apps.core.timeutil import trange

from .models import AvailabilityRule, Blackout, BookingPolicy, Quota, RestrictionTier, Scope, Weekday

ROLE_PLURAL = {
    Role.STUDENT: "students",
    Role.FACULTY: "faculty",
    Role.STAFF: "staff",
    Role.CUSTODIAN: "custodians",
    Role.DEPT_HEAD: "heads of department",
    Role.FACILITY_MANAGER: "facility managers",
    Role.ADMIN: "administrators",
}
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def minutes_label(m: int | None) -> str:
    if not m:
        return "0 min"
    if m % 1440 == 0:
        d = m // 1440
        return f"{d} day{'s' if d != 1 else ''}"
    h, mm = divmod(m, 60)
    if h and mm:
        return f"{h} h {mm} min"
    return f"{h} h" if h else f"{mm} min"


def roles_phrase(roles, *, empty="everyone") -> str:
    names = [ROLE_PLURAL.get(r, r) for r in roles or []]
    if not names:
        return empty
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def scope_phrase(obj) -> str:
    if obj.scope == Scope.RESOURCE and obj.resource_id:
        return f"{obj.resource.name}"
    if obj.scope == Scope.TYPE and obj.resource_type_id:
        return f"all {obj.resource_type.plural or obj.resource_type.name}"
    building = getattr(obj, "building", None)
    if building:
        return f"everything in {building.name}"
    return "the whole campus"


# ── Plain-English summaries ─────────────────────────────────────────────────


def describe_policy(p: BookingPolicy) -> str:
    bits = [
        f"Book in {p.slot_minutes}-minute steps, {minutes_label(p.min_duration_minutes)} to "
        f"{minutes_label(p.max_duration_minutes)} at a time"
    ]
    if p.lead_time_minutes:
        bits.append(f"at least {minutes_label(p.lead_time_minutes)} ahead")
    bits.append(f"up to {p.max_advance_days} days out")
    s = ", ".join(bits) + "."
    if p.requires_checkin:
        s += (
            f" Check in from {p.checkin_opens_minutes} min before the start; unclaimed bookings are released "
            f"{p.checkin_grace_minutes} min after it."
        )
    else:
        s += " No check-in needed."
    if not p.enforce_capacity:
        s += " Capacity isn't enforced."
    return s


def describe_quota(q: Quota) -> str:
    who = (
        f"{q.department.code} department, shared by all its members"
        if q.department_id
        else f"each {Role(q.role).label.lower()}"
        if q.role
        else "everyone"
    )
    limits = []
    if q.max_hours is not None:
        limits.append(f"{q.max_hours:g} hour{'s' if q.max_hours != 1 else ''}")
    if q.max_bookings is not None:
        limits.append(f"{q.max_bookings} booking{'s' if q.max_bookings != 1 else ''}")
    what = f" of {q.resource_type.plural or q.resource_type.name}" if q.resource_type_id else ""
    return f"Up to {' and '.join(limits)}{what} {q.get_period_display()}, for {who}."


def describe_tier(t: RestrictionTier) -> str:
    result = f"a {t.restrict_days}-day booking pause" if t.restrict_days else "a warning only"
    return f"{t.no_shows} unforgiven no-show{'s' if t.no_shows != 1 else ''} within {t.window_days} days leads to {result}."


def describe_blackout(b: Blackout) -> str:
    s = f"Bookings for {scope_phrase(b)} are refused"
    if b.exempt_roles:
        s += f", except for {roles_phrase(b.exempt_roles)}"
    return s + ". Facility managers and administrators can still book."


# ── Scope handling shared by policies, hours and blackouts ──────────────────


class ScopedFormMixin:
    """Keeps scope / resource_type / resource consistent (the DB check constraint, in a sentence)."""

    def setup_scope(self, institution_id):
        self.fields["resource_type"].queryset = ResourceType.objects.filter(institution_id=institution_id)
        self.fields["resource"].queryset = Resource.objects.filter(institution_id=institution_id).order_by("code")
        self.fields["resource_type"].required = False
        self.fields["resource"].required = False
        self.fields["resource_type"].empty_label = "Choose a type"
        self.fields["resource"].empty_label = "Choose a resource"
        self.fields["resource"].label_from_instance = lambda r: f"{r.code}, {r.name}"

    def clean_scope_fields(self, data):
        scope = data.get("scope")
        if scope == Scope.TYPE:
            if not data.get("resource_type"):
                self.add_error("resource_type", "Choose which type of resource this applies to.")
            data["resource"] = None
        elif scope == Scope.RESOURCE:
            if not data.get("resource"):
                self.add_error("resource", "Choose the resource this applies to.")
            data["resource_type"] = None
        else:
            data["resource_type"] = None
            data["resource"] = None
        return data


SLOT_CHOICES = [
    (5, "5 minutes"),
    (10, "10 minutes"),
    (15, "15 minutes"),
    (20, "20 minutes"),
    (30, "30 minutes"),
    (60, "1 hour"),
]
LEAD_CHOICES = [
    (0, "No notice needed"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (60, "1 hour"),
    (120, "2 hours"),
    (240, "4 hours"),
    (720, "12 hours"),
    (1440, "1 day"),
    (2880, "2 days"),
    (4320, "3 days"),
    (10080, "1 week"),
]


def _with_current(choices, value):
    if value is not None and value not in {c for c, _ in choices}:
        return sorted([*choices, (value, minutes_label(value))])
    return choices


class BookingPolicyForm(StyledFormMixin, ScopedFormMixin, forms.ModelForm):
    slot_minutes = forms.TypedChoiceField(coerce=int, choices=SLOT_CHOICES, label="Booking steps")
    lead_time_minutes = forms.TypedChoiceField(coerce=int, choices=LEAD_CHOICES, label="Minimum notice")

    class Meta:
        model = BookingPolicy
        fields = [
            "scope",
            "resource_type",
            "resource",
            "slot_minutes",
            "min_duration_minutes",
            "max_duration_minutes",
            "lead_time_minutes",
            "max_advance_days",
            "requires_checkin",
            "checkin_opens_minutes",
            "checkin_grace_minutes",
            "enforce_capacity",
        ]
        labels = {
            "scope": "Applies to",
            "resource_type": "Type",
            "resource": "Resource",
            "min_duration_minutes": "Shortest booking (min)",
            "max_duration_minutes": "Longest booking (min)",
            "max_advance_days": "Opens this many days ahead",
            "requires_checkin": "Require check-in",
            "checkin_opens_minutes": "Check-in opens (min before)",
            "checkin_grace_minutes": "Release after (min)",
            "enforce_capacity": "Refuse bookings above capacity",
        }
        widgets = {
            f: forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"})
            for f in (
                "min_duration_minutes",
                "max_duration_minutes",
                "max_advance_days",
                "checkin_opens_minutes",
                "checkin_grace_minutes",
            )
        }

    def __init__(self, *args, institution_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.setup_scope(institution_id)
        self.fields["slot_minutes"].choices = _with_current(
            SLOT_CHOICES, self.instance.slot_minutes if self.instance.pk else None
        )
        self.fields["lead_time_minutes"].choices = _with_current(
            LEAD_CHOICES, self.instance.lead_time_minutes if self.instance.pk else None
        )
        self.style()

    def clean(self):
        data = self.clean_scope_fields(super().clean())
        slot, lo, hi = data.get("slot_minutes"), data.get("min_duration_minutes"), data.get("max_duration_minutes")
        if lo is not None and hi is not None and lo > hi:
            self.add_error("max_duration_minutes", "The longest booking can't be shorter than the shortest one.")
        if slot and lo is not None and hi is not None:
            for name, v in (("min_duration_minutes", lo), ("max_duration_minutes", hi)):
                if v < slot or v % slot:
                    self.add_error(
                        name, f"Use whole steps: with {slot}-minute steps, {slot}, {slot * 2}, {slot * 3} and so on."
                    )
        if data.get("max_advance_days") == 0:
            self.add_error("max_advance_days", "Allow at least 1 day, or nobody can book ahead at all.")
        if not self.errors:
            clash = BookingPolicy.objects.filter(
                institution_id=self.institution_id,
                scope=data.get("scope"),
                resource_type=data.get("resource_type"),
                resource=data.get("resource"),
            )
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise ValidationError("There's already a policy for exactly this; edit that one instead.")
        return data


class HoursForm(StyledFormMixin, ScopedFormMixin, forms.Form):
    scope = forms.ChoiceField(choices=Scope.choices, label="Applies to")
    resource_type = forms.ModelChoiceField(queryset=ResourceType.objects.none(), label="Type")
    resource = forms.ModelChoiceField(queryset=Resource.objects.none(), label="Resource")
    weekdays = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=Weekday.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Days",
        error_messages={"required": "Pick at least one day."},
    )
    opens = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        label="Opens",
        error_messages={"required": "Say when it opens.", "invalid": "Enter a time like 08:00."},
    )
    closes = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        label="Closes",
        error_messages={"required": "Say when it closes.", "invalid": "Enter a time like 20:00."},
    )

    def __init__(self, *args, institution_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.setup_scope(institution_id)
        self.style()

    def clean(self):
        data = self.clean_scope_fields(super().clean())
        o, c = data.get("opens"), data.get("closes")
        if o and c and o >= c:
            self.add_error("closes", "Closing time must be after opening time (overnight hours aren't supported).")
        if self.errors:
            return data
        existing = AvailabilityRule.objects.filter(
            institution_id=self.institution_id,
            scope=data["scope"],
            resource_type=data.get("resource_type"),
            resource=data.get("resource"),
            weekday__in=data["weekdays"],
            opens__lt=c,
            closes__gt=o,
        )
        clash = existing.first()
        if clash:
            raise ValidationError(
                f"{clash.get_weekday_display()} already has {clash.opens:%H:%M}–{clash.closes:%H:%M} here. "
                "Remove it first, or pick times that don't overlap."
            )
        return data

    def save(self) -> list[AvailabilityRule]:
        d = self.cleaned_data
        return AvailabilityRule.objects.bulk_create(
            [
                AvailabilityRule(
                    institution_id=self.institution_id,
                    scope=d["scope"],
                    resource_type=d.get("resource_type"),
                    resource=d.get("resource"),
                    weekday=wd,
                    opens=d["opens"],
                    closes=d["closes"],
                )
                for wd in sorted(set(d["weekdays"]))
            ]
        )


DT_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class BlackoutForm(StyledFormMixin, ScopedFormMixin, forms.ModelForm):
    starts = forms.DateTimeField(
        widget=DT_WIDGET,
        label="From",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        error_messages={"required": "Say when it starts."},
    )
    ends = forms.DateTimeField(
        widget=DT_WIDGET,
        label="Until",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        error_messages={"required": "Say when it ends."},
    )
    exempt_roles = forms.MultipleChoiceField(
        choices=Role.choices, required=False, widget=forms.CheckboxSelectMultiple, label="Still allowed to book"
    )

    class Meta:
        model = Blackout
        fields = ["title", "kind", "scope", "building", "resource_type", "resource", "exempt_roles", "note"]
        labels = {"title": "Name", "kind": "Kind", "scope": "Applies to", "building": "Block", "note": "Note"}
        error_messages = {"title": {"required": "Give it a name people will understand, e.g. Diwali break."}}

    def __init__(self, *args, institution_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.setup_scope(institution_id)
        self.fields["building"].queryset = Building.objects.filter(institution_id=institution_id)
        self.fields["building"].required = False
        self.fields["building"].empty_label = "Every block"
        self.fields["building"].help_text = "Only for whole-campus blackouts: limit it to one block."
        if self.instance.pk and self.instance.period:
            self.initial["starts"] = timezone.localtime(self.instance.period.lower)
            self.initial["ends"] = timezone.localtime(self.instance.period.upper)
        self.style()

    def clean(self):
        data = self.clean_scope_fields(super().clean())
        if data.get("scope") != Scope.CAMPUS:
            data["building"] = None
        s, e = data.get("starts"), data.get("ends")
        if s and e and e <= s:
            self.add_error("ends", "The end must be after the start.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.institution_id = self.institution_id
        obj.period = trange(self.cleaned_data["starts"], self.cleaned_data["ends"])
        if commit:
            obj.save()
        return obj


class QuotaForm(StyledFormMixin, forms.ModelForm):
    TARGETS = [("role", "Each person with a role"), ("department", "A department, shared")]
    target = forms.ChoiceField(choices=TARGETS, widget=forms.RadioSelect, label="Who it limits")

    class Meta:
        model = Quota
        fields = ["name", "role", "department", "resource_type", "period", "max_hours", "max_bookings", "active"]
        labels = {
            "name": "Name",
            "role": "Role",
            "department": "Department",
            "resource_type": "Only for this type",
            "period": "Resets",
            "max_hours": "Most hours",
            "max_bookings": "Most bookings",
            "active": "Active",
        }
        widgets = {
            "max_hours": forms.NumberInput(attrs={"min": 0.5, "step": 0.5, "inputmode": "decimal"}),
            "max_bookings": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
        }
        error_messages = {"name": {"required": "Give the quota a name, e.g. Student lab hours."}}

    def __init__(self, *args, user, **kwargs):
        from apps.accounts.permissions import is_campus_wide

        super().__init__(*args, **kwargs)
        inst = user.institution_id
        self.user = user
        self.fields["department"].queryset = Department.objects.filter(institution_id=inst)
        self.fields["resource_type"].queryset = ResourceType.objects.filter(institution_id=inst)
        self.fields["resource_type"].empty_label = "Every type"
        self.fields["department"].empty_label = "Choose a department"
        self.fields["role"].choices = [("", "Choose a role"), *Role.choices]
        self.fields["period"].choices = [
            (v, label.replace("per ", "Every ").capitalize()) for v, label in self.fields["period"].choices
        ]
        self.department_only = not is_campus_wide(user)
        if self.department_only:
            # Heads of department manage their own department's shared quota, nothing else.
            self.fields["department"].queryset = Department.objects.filter(pk=user.department_id)
            self.fields["department"].disabled = True
            self.fields["department"].help_text = "Heads of department set quotas for their own department."
            self.fields["target"].choices = [("department", "My department, shared")]
            self.fields["target"].disabled = True
            self.fields["role"].disabled = True
            self.initial["target"] = "department"
            self.initial["department"] = user.department_id
        else:
            self.initial.setdefault("target", "department" if self.instance.department_id else "role")
        self.style()

    def clean(self):
        data = super().clean()
        target = "department" if self.department_only else data.get("target")
        if target == "department":
            data["role"] = ""
            if self.department_only:
                data["department"] = Department.objects.filter(pk=self.user.department_id).first()
            if not data.get("department"):
                self.add_error("department", "Choose the department whose bookings this limits.")
        else:
            data["department"] = None
            if not data.get("role"):
                self.add_error("role", "Choose the role this limits.")
        if data.get("max_hours") is None and data.get("max_bookings") is None:
            raise ValidationError("Set a limit on hours, bookings, or both.")
        if data.get("max_hours") is not None and data["max_hours"] <= 0:
            self.add_error("max_hours", "Use a number of hours above zero.")
        if data.get("max_bookings") == 0:
            self.add_error("max_bookings", "Use at least 1 booking, or leave it empty for no count limit.")
        return data


class RestrictionTierForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = RestrictionTier
        fields = ["no_shows", "window_days", "restrict_days", "label"]
        labels = {
            "no_shows": "No-shows",
            "window_days": "Within (days)",
            "restrict_days": "Pause booking for (days)",
            "label": "Label",
        }
        help_texts = {"restrict_days": "0 means a warning only."}
        widgets = {
            f: forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"})
            for f in ("no_shows", "window_days", "restrict_days")
        }

    def __init__(self, *args, institution_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.style()

    def clean(self):
        data = super().clean()
        n = data.get("no_shows")
        if n is not None and n < 1:
            self.add_error("no_shows", "Start the ladder at 1 no-show or more.")
        if data.get("window_days") is not None and data["window_days"] < 1:
            self.add_error("window_days", "Look back at least 1 day.")
        if n:
            clash = RestrictionTier.objects.filter(institution_id=self.institution_id, no_shows=n)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("no_shows", f"There's already a step at {n} no-shows; edit that one instead.")
        return data


def week_rows(rules, start_hour=6, end_hour=23):
    """Seven rows of positioned bars for the opening-hours grid."""
    span = (end_hour - start_hour) * 60
    by_day = {wd: [] for wd in range(7)}
    for r in rules:
        by_day[r.weekday].append(r)
    rows = []
    for wd in range(7):
        bars = []
        for r in sorted(by_day[wd], key=lambda x: x.opens):
            o = max(0, (r.opens.hour * 60 + r.opens.minute) - start_hour * 60)
            c = min(span, (r.closes.hour * 60 + r.closes.minute) - start_hour * 60)
            bars.append({"rule": r, "left": o / span * 100, "width": max(0, c - o) / span * 100})
        rows.append({"day": WEEKDAY_SHORT[wd], "weekday": wd, "bars": bars})
    return rows


def parse_local(value: str) -> datetime | None:
    try:
        return timezone.make_aware(datetime.strptime(value, "%Y-%m-%dT%H:%M"))
    except (TypeError, ValueError):
        return None
