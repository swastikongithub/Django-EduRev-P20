from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Department, User
from .permissions import ROLE_PERMISSIONS, has_cap


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "code", "name", "school"]


class QuotaUsageSerializer(serializers.Serializer):
    name = serializers.CharField(source="quota.name")
    period = serializers.CharField(source="quota.period")
    departmental = serializers.BooleanField(source="quota.is_departmental")
    resource_type = serializers.CharField(source="quota.resource_type.code", default=None, allow_null=True)
    window_start = serializers.SerializerMethodField()
    window_end = serializers.SerializerMethodField()
    hours_used = serializers.DecimalField(max_digits=7, decimal_places=1)
    max_hours = serializers.DecimalField(source="quota.max_hours", max_digits=6, decimal_places=1, allow_null=True)
    bookings_used = serializers.IntegerField()
    max_bookings = serializers.IntegerField(source="quota.max_bookings", allow_null=True)
    pct = serializers.IntegerField(help_text="Highest share of any limit used, 0-100")

    @extend_schema_field(serializers.DateTimeField())
    def get_window_start(self, obj):
        return serializers.DateTimeField().to_representation(obj.window[0])

    @extend_schema_field(serializers.DateTimeField())
    def get_window_end(self, obj):
        return serializers.DateTimeField().to_representation(obj.window[1])


class RestrictionSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    reason = serializers.CharField()
    tier_label = serializers.CharField()


class MeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name")
    role_display = serializers.CharField(source="get_role_display")
    department = DepartmentSerializer(allow_null=True)
    capabilities = serializers.SerializerMethodField()
    quotas = QuotaUsageSerializer(many=True, source="quota_usage")
    restriction = RestrictionSerializer(allow_null=True, source="active_restriction")
    unread_notifications = serializers.IntegerField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "name",
            "email",
            "vid",
            "role",
            "role_display",
            "department",
            "section",
            "programme",
            "designation",
            "capabilities",
            "quotas",
            "restriction",
            "unread_notifications",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_capabilities(self, obj):
        every = sorted(set().union(*ROLE_PERMISSIONS.values()))
        return [c for c in every if has_cap(obj, c)]
