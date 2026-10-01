from rest_framework import serializers

from .models import TimetablePublication


class TimetableRowSerializer(serializers.Serializer):
    """One class row, as pushed by P13. Values are parsed (and row errors reported) by the timetable service."""

    room_code = serializers.CharField(max_length=32)
    day = serializers.CharField(max_length=12, help_text="Mon..Sun, or 0 (Monday) .. 6")
    start = serializers.CharField(max_length=12, help_text="HH:MM")
    end = serializers.CharField(max_length=12, help_text="HH:MM")
    course_code = serializers.CharField(max_length=16)
    course_title = serializers.CharField(max_length=160, required=False, allow_blank=True)
    section = serializers.CharField(max_length=24, required=False, allow_blank=True)
    faculty = serializers.CharField(max_length=120, required=False, allow_blank=True)
    kind = serializers.CharField(
        max_length=16, required=False, allow_blank=True, help_text="Lecture | Practical | Tutorial"
    )


class PublishRequestSerializer(serializers.Serializer):
    term = serializers.CharField(max_length=16, help_text="UMS term code, e.g. 26271")
    entries = TimetableRowSerializer(many=True, allow_empty=False, max_length=20000)


class PublicationSerializer(serializers.ModelSerializer):
    term = serializers.CharField(source="term.code", read_only=True)
    published_by = serializers.CharField(
        source="published_by.display_name", default=None, allow_null=True, read_only=True
    )

    class Meta:
        model = TimetablePublication
        fields = [
            "id",
            "term",
            "version",
            "source",
            "status",
            "entry_count",
            "occurrence_count",
            "displaced_count",
            "published_at",
            "published_by",
            "created_at",
        ]
        read_only_fields = fields


class PublishResultSerializer(serializers.Serializer):
    publication = PublicationSerializer()
    occurrences = serializers.IntegerField(help_text="Class occurrences written to the availability ledger")
    displaced = serializers.IntegerField(help_text="Ordinary bookings cancelled because a class now owns the time")
    superseded = serializers.IntegerField(help_text="Previously published versions replaced")
