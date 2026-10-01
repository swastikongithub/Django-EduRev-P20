from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.catalogue.models import Resource, ResourceStatus
from apps.catalogue.serializers import ResourceRefSerializer

from .models import Booking, BookingSeries, Frequency


class InstitutionScopedMixin:
    """Restrict relational inputs to the requesting user's institution."""

    def scope_field(self, name, queryset):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields[name].queryset = queryset.filter(institution_id=request.user.institution_id)


class ApprovalStepSerializer(serializers.Serializer):
    step = serializers.IntegerField(source="step_order")
    approver_role = serializers.CharField()
    decision = serializers.CharField()
    decided_by = serializers.CharField(source="decided_by.display_name", default=None, allow_null=True)
    comment = serializers.CharField()
    due_at = serializers.DateTimeField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)


class BookingSerializer(serializers.ModelSerializer):
    resource = ResourceRefSerializer(read_only=True)
    start = serializers.DateTimeField(read_only=True)
    end = serializers.DateTimeField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requester = serializers.CharField(source="requester.display_name", read_only=True)
    booked_for = serializers.CharField(source="booked_for.display_name", read_only=True)
    series = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "reference",
            "resource",
            "title",
            "start",
            "end",
            "status",
            "status_display",
            "status_reason",
            "attendees",
            "group_label",
            "requester",
            "booked_for",
            "series",
            "requires_checkin",
            "checked_in_at",
            "checked_out_at",
            "created_at",
        ]
        read_only_fields = fields


class CheckinStateSerializer(serializers.Serializer):
    state = serializers.CharField(help_text="in_use, inactive, not_required, not_yet, open, missed")
    opens = serializers.DateTimeField(required=False)
    closes = serializers.DateTimeField(required=False)
    ends = serializers.DateTimeField(required=False)
    seconds_left = serializers.IntegerField(required=False)


class BookingDetailSerializer(BookingSerializer):
    approvals = ApprovalStepSerializer(many=True, read_only=True)
    checkin = serializers.SerializerMethodField()
    qr_token = serializers.SerializerMethodField()

    class Meta(BookingSerializer.Meta):
        fields = [*BookingSerializer.Meta.fields, "notes", "approvals", "checkin", "qr_token"]
        read_only_fields = fields

    @extend_schema_field(CheckinStateSerializer)
    def get_checkin(self, obj):
        from apps.checkins.services import checkin_state

        return CheckinStateSerializer(checkin_state(obj)).data

    @extend_schema_field(OpenApiTypes.STR)
    def get_qr_token(self, obj):
        """The pass token is only shown to the person the booking is for."""
        request = self.context.get("request")
        if request is not None and request.user.pk == obj.booked_for_id:
            return obj.qr_token
        return None


class BookingCreateSerializer(InstitutionScopedMixin, serializers.Serializer):
    resource = serializers.PrimaryKeyRelatedField(queryset=Resource.objects.exclude(status=ResourceStatus.RETIRED))
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    title = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    attendees = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    group_label = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    booked_for = serializers.SlugRelatedField(
        slug_field="username",
        queryset=User.objects.filter(is_active=True),
        required=False,
        help_text="Username of the person this is for (faculty/staff booking on behalf).",
    )
    items = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=1000),
        required=False,
        help_text="Inventory item id -> quantity to reserve with the booking.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scope_field("resource", self.fields["resource"].queryset)
        self.scope_field("booked_for", self.fields["booked_for"].queryset)

    def validate_items(self, value):
        if any(not str(k).isdigit() for k in value):
            raise serializers.ValidationError("Item keys must be numeric item ids.")
        return {int(k): v for k, v in value.items()}

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "The end time must be after the start time."})
        return attrs


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class ApproveSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class RejectSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=500, help_text="Required: tell the requester why.")


class CheckInSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=[("app", "Tapped check-in in app"), ("custodian", "Checked in by custodian")], default="app"
    )


# ── Recurring series ────────────────────────────────────────────────────────


class SeriesRequestSerializer(InstitutionScopedMixin, serializers.Serializer):
    resource = serializers.PrimaryKeyRelatedField(queryset=Resource.objects.exclude(status=ResourceStatus.RETIRED))
    title = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    frequency = serializers.ChoiceField(choices=Frequency.choices, default=Frequency.WEEKLY)
    interval = serializers.IntegerField(min_value=1, max_value=8, default=1)
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        default=list,
        max_length=7,
        help_text="0 = Monday ... 6 = Sunday (weekly only; defaults to the start date's weekday)",
    )
    start_date = serializers.DateField()
    until_date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    attendees = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    group_label = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    booked_for = serializers.SlugRelatedField(
        slug_field="username", queryset=User.objects.filter(is_active=True), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scope_field("resource", self.fields["resource"].queryset)
        self.scope_field("booked_for", self.fields["booked_for"].queryset)

    def validate(self, attrs):
        if attrs["until_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"until_date": "The series must end on or after its first date."})
        if (attrs["until_date"] - attrs["start_date"]).days > 366:
            raise serializers.ValidationError({"until_date": "A series can span at most one year."})
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "The end time must be after the start time."})
        attrs["weekdays"] = sorted(set(attrs.get("weekdays") or []))
        return attrs

    def occurrence_kwargs(self):
        d = self.validated_data
        return {
            k: d[k] for k in ("frequency", "interval", "weekdays", "start_date", "until_date", "start_time", "end_time")
        }


class OccurrencePlanSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    ok = serializers.BooleanField()
    code = serializers.CharField(help_text="Why it can't be booked (conflict, timetable, closed, ...)")
    reason = serializers.CharField()
    alternatives = ResourceRefSerializer(many=True)


class SeriesPreviewSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    bookable = serializers.IntegerField()
    occurrences = OccurrencePlanSerializer(many=True)


class SkippedOccurrenceSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    code = serializers.CharField()
    reason = serializers.CharField()


class BookingSeriesSerializer(serializers.ModelSerializer):
    resource = ResourceRefSerializer(read_only=True)
    skipped = SkippedOccurrenceSerializer(many=True, read_only=True)

    class Meta:
        model = BookingSeries
        fields = [
            "id",
            "resource",
            "title",
            "frequency",
            "interval",
            "weekdays",
            "start_date",
            "until_date",
            "start_time",
            "end_time",
            "group_label",
            "created_count",
            "skipped",
            "created_at",
        ]
        read_only_fields = fields


class SeriesResultSerializer(serializers.Serializer):
    series = BookingSeriesSerializer()
    created = BookingSerializer(many=True)
    skipped = SkippedOccurrenceSerializer(many=True)
