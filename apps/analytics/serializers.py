from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

DIMENSIONS = ["type", "resource", "department", "building"]
MAX_RANGE_DAYS = 366


class UtilisationQuerySerializer(serializers.Serializer):
    start = serializers.DateField(required=False, help_text="First day (default: 30 days ago)")
    end = serializers.DateField(required=False, help_text="Last day, inclusive (default: yesterday)")
    by = serializers.ChoiceField(choices=DIMENSIONS, default="type")
    department = serializers.CharField(
        required=False, max_length=16, help_text="Department code (campus analysts only; others see their own)"
    )
    type = serializers.CharField(required=False, max_length=40, help_text="Restrict to one resource type code")

    def validate(self, attrs):
        yesterday = timezone.localdate() - timedelta(days=1)
        attrs["end"] = attrs.get("end") or yesterday
        attrs["start"] = attrs.get("start") or attrs["end"] - timedelta(days=29)
        if attrs["end"] < attrs["start"]:
            raise serializers.ValidationError({"end": "end must be on or after start."})
        if (attrs["end"] - attrs["start"]).days >= MAX_RANGE_DAYS:
            raise serializers.ValidationError({"start": f"The range can be at most {MAX_RANGE_DAYS} days."})
        return attrs


class MetricsSerializer(serializers.Serializer):
    open_hours = serializers.FloatField()
    class_hours = serializers.FloatField()
    maintenance_hours = serializers.FloatField()
    booked_hours = serializers.FloatField()
    used_hours = serializers.FloatField()
    released_hours = serializers.FloatField()
    idle_hours = serializers.FloatField()
    utilisation_pct = serializers.FloatField()
    realised_pct = serializers.FloatField()
    bookings = serializers.IntegerField()
    no_shows = serializers.IntegerField()
    no_show_rate_pct = serializers.FloatField()
    cancellations = serializers.IntegerField()
    denied_attempts = serializers.IntegerField()


class UtilisationRowSerializer(MetricsSerializer):
    key = serializers.IntegerField(allow_null=True, help_text="Id of the resource/type/department/building")
    label = serializers.CharField()
    resources = serializers.IntegerField()


class OverviewSerializer(MetricsSerializer):
    resources = serializers.IntegerField()
    days = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    avg_turnaround_hours = serializers.FloatField(allow_null=True)
    top_resource = UtilisationRowSerializer(allow_null=True)


class ScopeSerializer(serializers.Serializer):
    department = serializers.CharField(allow_null=True, help_text="Department code, or null for campus-wide")
    type = serializers.CharField(allow_null=True)


class UtilisationReportSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    by = serializers.CharField()
    scope = ScopeSerializer()
    overview = OverviewSerializer()
    rows = UtilisationRowSerializer(many=True)
