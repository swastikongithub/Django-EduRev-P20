from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Building, Feature, Resource, ResourceAttribute, ResourceType


class ResourceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceType
        fields = ["id", "code", "name", "plural", "category"]


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "code", "name", "zone"]


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "name", "icon"]


class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceAttribute
        fields = ["key", "value"]


class ResourceRefSerializer(serializers.ModelSerializer):
    """Compact reference embedded in bookings, windows and suggestions."""

    class Meta:
        model = Resource
        fields = ["id", "code", "slug", "name"]


class ResourceSerializer(serializers.ModelSerializer):
    type = ResourceTypeSerializer(read_only=True)
    building = BuildingSerializer(read_only=True)
    department = serializers.SlugRelatedField(slug_field="code", read_only=True)
    features = FeatureSerializer(many=True, read_only=True)
    location = serializers.CharField(source="location_label", read_only=True)
    available_for_booking = serializers.BooleanField(source="is_available_for_booking", read_only=True)

    class Meta:
        model = Resource
        fields = [
            "id",
            "code",
            "slug",
            "name",
            "tagline",
            "type",
            "capacity",
            "building",
            "floor",
            "room",
            "location",
            "department",
            "features",
            "status",
            "status_note",
            "is_bookable",
            "available_for_booking",
        ]


class ResourceDetailSerializer(ResourceSerializer):
    attributes = AttributeSerializer(many=True, read_only=True)

    class Meta(ResourceSerializer.Meta):
        fields = [*ResourceSerializer.Meta.fields, "description", "attributes"]


# ── Availability ────────────────────────────────────────────────────────────


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False, help_text="First day (YYYY-MM-DD). Defaults to today.")
    days = serializers.IntegerField(required=False, default=1, min_value=1, max_value=7)

    def validate_date(self, value):
        today = timezone.localdate()
        if value < today - timedelta(days=31) or value > today + timedelta(days=366):
            raise serializers.ValidationError("Pick a date within the next year.")
        return value


class CellSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    state = serializers.CharField(help_text="free, mine, booked, pending, class, maintenance, blackout, closed, ...")
    reason = serializers.CharField(help_text="Why the cell is in this state, in words")
    selectable = serializers.BooleanField()


class BlockSerializer(serializers.Serializer):
    kind = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    label = serializers.CharField()
    reference = serializers.CharField(help_text="Booking reference, only for your own bookings or managers")


class DayScheduleSerializer(serializers.Serializer):
    date = serializers.DateField(source="day")
    is_open = serializers.BooleanField()
    open_minutes = serializers.IntegerField()
    free_minutes = serializers.IntegerField()
    cells = CellSerializer(many=True)
    blocks = BlockSerializer(many=True)


class AvailabilitySerializer(serializers.Serializer):
    resource = ResourceRefSerializer()
    days = DayScheduleSerializer(many=True)
