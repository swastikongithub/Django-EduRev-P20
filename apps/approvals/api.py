"""M5 — Approval queue API. Decisions are made through /bookings/{reference}/approve|reject/."""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.api import HasCap, StandardPagination

from .models import Approval
from .serializers import ApprovalQueueItemSerializer
from .services import queue_for


@extend_schema(tags=["approvals"])
@extend_schema_view(list=extend_schema(summary="Approval steps I can decide now, soonest booking first"))
class ApprovalQueueViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ApprovalQueueItemSerializer
    permission_classes = [IsAuthenticated, HasCap("approve_bookings")]
    pagination_class = StandardPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Approval.objects.none()
        return queue_for(self.request.user).select_related("booking__requester")
