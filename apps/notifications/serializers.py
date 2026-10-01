from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    unread = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "url", "tone", "created_at", "read_at", "unread"]
        read_only_fields = fields

    def get_unread(self, obj) -> bool:
        return obj.read_at is None


class ReadAllResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField(help_text="Notifications marked read")
