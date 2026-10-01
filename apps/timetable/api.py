"""M4 — Timetable API: P13 pushes a term's timetable as JSON; it is validated, staged and published atomically."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.api import HasCap, StandardPagination, error_responses
from apps.core.errors import BookingRejected

from .models import AcademicTerm, TimetablePublication
from .serializers import PublicationSerializer, PublishRequestSerializer, PublishResultSerializer
from .services import import_and_publish


@extend_schema(tags=["timetable"])
@extend_schema_view(list=extend_schema(summary="Timetable publications, newest first"))
class PublicationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PublicationSerializer
    permission_classes = [IsAuthenticated, HasCap("manage_timetable")]
    pagination_class = StandardPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TimetablePublication.objects.none()
        return (
            TimetablePublication.objects.filter(institution_id=self.request.user.institution_id)
            .select_related("term", "published_by")
            .order_by("-created_at")
        )

    @extend_schema(
        summary="Publish a term timetable (P13 push)",
        description="All-or-nothing: if any row is invalid nothing is published and every row error is returned "
        "(422, code `invalid_rows`, `detail.rows`). Publishing supersedes the term's previous version and "
        "cancels ordinary bookings that the new classes override.",
        request=PublishRequestSerializer,
        responses={201: PublishResultSerializer, **error_responses(400, 403, 404, 422)},
    )
    def create(self, request):
        body = PublishRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        term = get_object_or_404(
            AcademicTerm, institution_id=request.user.institution_id, code=body.validated_data["term"]
        )
        rows = [dict(row) for row in body.validated_data["entries"]]
        result = import_and_publish(term, rows, actor=request.user, fmt_source="p13-api", request=request)
        if result["errors"]:
            n = len(result["errors"])
            raise BookingRejected(
                f"{n} problem{'s' if n != 1 else ''} in the timetable; nothing was published.",
                code="invalid_rows",
                detail={"rows": result["errors"]},
            )
        return Response(PublishResultSerializer(result).data, status=status.HTTP_201_CREATED)
