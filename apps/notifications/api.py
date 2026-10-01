"""The caller's notification inbox. Nobody can read anyone else's notifications."""

import django_filters
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import StandardPagination, error_responses

from .models import Notification
from .serializers import NotificationSerializer, ReadAllResultSerializer
from .services import mark_all_read


class NotificationFilter(django_filters.FilterSet):
    unread = django_filters.BooleanFilter(field_name="read_at", lookup_expr="isnull", help_text="Only unread")
    kind = django_filters.CharFilter()

    class Meta:
        model = Notification
        fields = []


@extend_schema(tags=["notifications"])
@extend_schema_view(list=extend_schema(summary="My notifications, newest first"))
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    @extend_schema(summary="Mark all my notifications read", request=None, responses={200: ReadAllResultSerializer})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        return Response({"updated": mark_all_read(request.user)})

    @extend_schema(
        summary="Mark one notification read",
        request=None,
        responses={200: NotificationSerializer, **error_responses(404)},
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        note = self.get_object()
        if note.read_at is None:
            note.read_at = timezone.now()
            note.save(update_fields=["read_at"])
        return Response(NotificationSerializer(note).data)
