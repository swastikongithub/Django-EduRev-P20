from rest_framework import serializers

from apps.catalogue.models import Resource, ResourceStatus
from apps.catalogue.serializers import ResourceRefSerializer

from .models import BreakdownReport, MaintenanceKind, MaintenanceWindow, Severity


class MaintenanceWindowSerializer(serializers.ModelSerializer):
    resource = ResourceRefSerializer(read_only=True)
    start = serializers.DateTimeField(read_only=True)
    end = serializers.DateTimeField(read_only=True)
    created_by = serializers.CharField(source="created_by.display_name", default=None, allow_null=True, read_only=True)

    class Meta:
        model = MaintenanceWindow
        fields = [
            "id",
            "resource",
            "title",
            "kind",
            "start",
            "end",
            "status",
            "notes",
            "vendor",
            "created_by",
            "displaced_bookings",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class MaintenanceCreateSerializer(serializers.Serializer):
    resource = serializers.PrimaryKeyRelatedField(queryset=Resource.objects.exclude(status=ResourceStatus.RETIRED))
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    title = serializers.CharField(max_length=140)
    kind = serializers.ChoiceField(choices=MaintenanceKind.choices, default=MaintenanceKind.PREVENTIVE)
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    vendor = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            field = self.fields["resource"]
            field.queryset = field.queryset.filter(institution_id=request.user.institution_id)

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "Maintenance must end after it starts."})
        return attrs


class BreakdownCreateSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=160)
    details = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    severity = serializers.ChoiceField(choices=Severity.choices, default=Severity.HIGH)


class BreakdownReportSerializer(serializers.ModelSerializer):
    resource = ResourceRefSerializer(read_only=True)
    window = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = BreakdownReport
        fields = ["id", "resource", "summary", "details", "severity", "status", "window", "created_at"]
        read_only_fields = fields
