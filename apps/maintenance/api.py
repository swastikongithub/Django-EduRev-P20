"""M7 — Maintenance API: windows on resources the caller manages, and breakdown reports from anyone."""

import django_filters
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import is_campus_wide
from apps.catalogue.api import ID_OR_SLUG, get_resource
from apps.core.api import HasCap, StandardPagination, error_responses

from . import services
from .models import MaintenanceWindow, WindowStatus
from .serializers import (
    BreakdownCreateSerializer,
    BreakdownReportSerializer,
    MaintenanceCreateSerializer,
    MaintenanceWindowSerializer,
)


def managed_windows(user):
    """Windows on resources this user may operate (mirrors accounts.permissions.can_manage_resource)."""
    qs = MaintenanceWindow.objects.filter(institution_id=user.institution_id)
    if is_campus_wide(user):
        return qs
    q = Q(pk__in=[])
    if user.role == Role.CUSTODIAN:
        q = Q(resource__custodians__user=user)
    elif user.role == Role.DEPT_HEAD and user.department_id:
        q = Q(resource__department_id=user.department_id)
    return qs.filter(q).distinct()


class MaintenanceFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=WindowStatus.choices)
    resource = django_filters.NumberFilter(field_name="resource_id")

    class Meta:
        model = MaintenanceWindow
        fields = []


@extend_schema(tags=["maintenance"])
@extend_schema_view(
    list=extend_schema(summary="Maintenance windows on resources I manage"),
    retrieve=extend_schema(summary="Maintenance window detail"),
)
class MaintenanceViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    serializer_class = MaintenanceWindowSerializer
    permission_classes = [IsAuthenticated, HasCap("manage_maintenance")]
    filterset_class = MaintenanceFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MaintenanceWindow.objects.none()
        return managed_windows(self.request.user).select_related("resource", "created_by")

    def get_serializer_class(self):
        return MaintenanceCreateSerializer if self.action == "create" else MaintenanceWindowSerializer

    @extend_schema(
        summary="Schedule maintenance (displaces overlapping bookings, whose owners are told)",
        request=MaintenanceCreateSerializer,
        responses={201: MaintenanceWindowSerializer, **error_responses(400, 403, 409, 422)},
    )
    def create(self, request):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        window = services.schedule(
            v["resource"],
            v["start"],
            v["end"],
            title=v["title"],
            kind=v["kind"],
            actor=request.user,
            notes=v["notes"],
            vendor=v["vendor"],
            request=request,
        )
        return Response(MaintenanceWindowSerializer(window).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Cancel a maintenance window (frees its time)",
        request=None,
        responses={200: MaintenanceWindowSerializer, **error_responses(403, 404, 409)},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        window = services.cancel(self.get_object(), request.user, request=request)
        return Response(MaintenanceWindowSerializer(window).data)

    @extend_schema(
        summary="Mark a maintenance window complete (hands unused time back)",
        request=None,
        responses={200: MaintenanceWindowSerializer, **error_responses(403, 404, 409)},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        window = services.complete(self.get_object(), request.user, request=request)
        return Response(MaintenanceWindowSerializer(window).data)


@extend_schema(tags=["maintenance"])
class ReportBreakdownView(APIView):
    """Anyone who can see a resource can report it broken; critical reports take it offline."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Report a breakdown",
        parameters=[ID_OR_SLUG],
        request=BreakdownCreateSerializer,
        responses={201: BreakdownReportSerializer, **error_responses(400, 404)},
    )
    def post(self, request, id_or_slug):
        resource = get_resource(request.user, id_or_slug)
        body = BreakdownCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        report = services.report_breakdown(resource, request.user, request=request, **body.validated_data)
        return Response(BreakdownReportSerializer(report).data, status=status.HTTP_201_CREATED)
