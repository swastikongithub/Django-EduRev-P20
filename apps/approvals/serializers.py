from rest_framework import serializers

from apps.bookings.serializers import BookingSerializer

from .models import Approval


class ApprovalQueueItemSerializer(serializers.ModelSerializer):
    booking = BookingSerializer(read_only=True)
    approver_role_display = serializers.CharField(source="get_approver_role_display", read_only=True)
    workflow = serializers.CharField(source="workflow.name", default=None, allow_null=True, read_only=True)

    class Meta:
        model = Approval
        fields = [
            "id",
            "booking",
            "step_order",
            "approver_role",
            "approver_role_display",
            "workflow",
            "due_at",
            "created_at",
        ]
        read_only_fields = fields
