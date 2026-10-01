"""
M3 — Booking API. Views parse input and call services; the services own every rule.

Bookings are addressed by their public reference (LR-XXXXXX), never by integer id,
so URLs can't be enumerated. Visibility is enforced twice: DRF permissions gate the
action and every lookup goes through `visible_bookings(user)` — a booking the caller
may not see is a 404, not a 403, so its existence isn't leaked either.
"""

from datetime import time, timedelta

import django_filters
from django.conf import settings
from django.db.models import Q
from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from ics import Calendar, Event
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.approvals.models import Decision
from apps.approvals.services import can_decide, decide
from apps.checkins import services as checkins
from apps.core.api import HasCap, StandardPagination, error_responses
from apps.core.errors import InvalidTransition
from apps.core.timeutil import aware

from . import services
from .models import Booking, BookingStatus
from .serializers import (
    ApproveSerializer,
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingSerializer,
    CancelSerializer,
    CheckInSerializer,
    RejectSerializer,
    SeriesPreviewSerializer,
    SeriesRequestSerializer,
    SeriesResultSerializer,
)

BOOKING_RELATED = ("resource", "resource__type", "requester", "booked_for")


class BookingFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(method="filter_status", help_text="Status(es), comma-separated")
    resource = django_filters.NumberFilter(field_name="resource_id", help_text="Resource id")
    date_from = django_filters.DateFilter(method="filter_from", help_text="Bookings starting on/after this date")
    date_to = django_filters.DateFilter(method="filter_to", help_text="Bookings starting on/before this date")
    mine = django_filters.BooleanFilter(method="filter_mine", help_text="Only bookings made by or for me")

    class Meta:
        model = Booking
        fields = []

    def filter_status(self, queryset, name, value):
        wanted = [s.strip() for s in value.split(",") if s.strip()]
        unknown = set(wanted) - set(BookingStatus.values)
        if unknown:
            raise ValidationError({"status": [f"Unknown status: {', '.join(sorted(unknown))}."]})
        return queryset.filter(status__in=wanted) if wanted else queryset

    def filter_from(self, queryset, name, value):
        return queryset.filter(period__startswith__gte=aware(value, time.min))

    def filter_to(self, queryset, name, value):
        return queryset.filter(period__startswith__lt=aware(value + timedelta(days=1), time.min))

    def filter_mine(self, queryset, name, value):
        me = self.request.user
        mine = Q(booked_for=me) | Q(requester=me)
        return queryset.filter(mine) if value else queryset.exclude(mine)


@extend_schema(tags=["bookings"])
@extend_schema_view(
    list=extend_schema(summary="Bookings visible to me (own, plus resources I manage)"),
    retrieve=extend_schema(summary="Booking detail", responses={200: BookingDetailSerializer, **error_responses(404)}),
)
class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_field = "reference"
    lookup_value_regex = "[A-Za-z0-9-]+"
    filterset_class = BookingFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        return services.visible_bookings(self.request.user).select_related(*BOOKING_RELATED).order_by("-period")

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        if self.action == "list":
            return BookingSerializer
        return BookingDetailSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasCap("book_resources")()]
        if self.action in ("approve", "reject"):
            return [IsAuthenticated(), HasCap("approve_bookings")()]
        return super().get_permissions()

    def _detail(self, booking, status_code=status.HTTP_200_OK):
        booking = (
            Booking.objects.select_related(*BOOKING_RELATED)
            .prefetch_related("approvals__decided_by")
            .get(pk=booking.pk)
        )
        return Response(
            BookingDetailSerializer(booking, context=self.get_serializer_context()).data, status=status_code
        )

    @extend_schema(
        summary="Book a resource",
        description="Atomic claim on the shared ledger. 409 when the time is taken (with the reason), "
        "422 when a rule forbids it (hours, quota, blackout, lead time, capacity...).",
        request=BookingCreateSerializer,
        responses={201: BookingDetailSerializer, **error_responses(400, 403, 409, 422)},
    )
    def create(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        booking = services.create_booking(
            requester=request.user,
            resource=v["resource"],
            start=v["start"],
            end=v["end"],
            title=v["title"],
            attendees=v["attendees"],
            booked_for=v.get("booked_for"),
            group_label=v["group_label"],
            notes=v["notes"],
            items=v.get("items") or None,
            request=request,
        )
        return self._detail(booking, status.HTTP_201_CREATED)

    @extend_schema(
        summary="Cancel a booking",
        request=CancelSerializer,
        responses={200: BookingDetailSerializer, **error_responses(403, 404)},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, reference=None):
        booking = self.get_object()
        body = CancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.cancel_booking(booking, request.user, reason=body.validated_data["reason"], request=request)
        return self._detail(booking)

    def _pending_approval(self, reference):
        """
        The booking and its current approval step. An approver may be named on a step
        without otherwise being able to see the booking, so either route grants access.
        """
        user = self.request.user
        booking = (
            Booking.objects.filter(institution_id=user.institution_id, reference=reference)
            .select_related("resource")
            .first()
        )
        if booking is None:
            raise Http404
        approval = booking.approvals.filter(decision=Decision.PENDING).order_by("step_order").first()
        visible = services.visible_bookings(user).filter(pk=booking.pk).exists()
        if not visible and not (approval and can_decide(user, approval)):
            raise Http404
        if booking.status != BookingStatus.PENDING or approval is None:
            raise InvalidTransition(
                f"This booking isn't awaiting approval (it is {booking.get_status_display().lower()})."
            )
        return booking, approval

    @extend_schema(
        summary="Approve the booking's current approval step",
        request=ApproveSerializer,
        responses={200: BookingDetailSerializer, **error_responses(403, 404, 409)},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, reference=None):
        body = ApproveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        booking, approval = self._pending_approval(reference)
        decide(approval, request.user, approve=True, comment=body.validated_data["comment"], request=request)
        return self._detail(booking)

    @extend_schema(
        summary="Reject the booking's current approval step (a comment is required)",
        request=RejectSerializer,
        responses={200: BookingDetailSerializer, **error_responses(400, 403, 404, 409)},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, reference=None):
        body = RejectSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        booking, approval = self._pending_approval(reference)
        decide(approval, request.user, approve=False, comment=body.validated_data["comment"], request=request)
        return self._detail(booking)

    @extend_schema(
        summary="Check in (from the app, or by the custodian)",
        request=CheckInSerializer,
        responses={200: BookingDetailSerializer, **error_responses(403, 404, 409)},
    )
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, reference=None):
        booking = self.get_object()
        body = CheckInSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        checkins.check_in(booking, request.user, method=body.validated_data["method"], request=request)
        return self._detail(booking)

    @extend_schema(
        summary="Check out early and hand the rest of the slot back",
        request=None,
        responses={200: BookingDetailSerializer, **error_responses(403, 404, 409)},
    )
    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, reference=None):
        booking = self.get_object()
        checkins.check_out(booking, request.user, request=request)
        return self._detail(booking)

    @extend_schema(
        summary="Download the booking as an iCalendar event",
        responses={(200, "text/calendar"): OpenApiResponse(OpenApiTypes.STR), **error_responses(404)},
    )
    @action(detail=True, methods=["get"])
    def ics(self, request, reference=None):
        booking = self.get_object()
        event = Event(
            name=f"{booking.title} · {booking.resource.name}",
            begin=booking.start,
            end=booking.end,
            uid=f"{booking.reference}@lpu-reserve",
            location=booking.resource.location_label or booking.resource.name,
            description=f"Booking {booking.reference} ({booking.get_status_display()}).\n"
            f"{settings.SITE_URL.rstrip('/')}{booking.get_absolute_url()}",
            created=booking.created_at,
            status="CANCELLED" if booking.status in (BookingStatus.CANCELLED, BookingStatus.REJECTED) else "CONFIRMED",
        )
        calendar = Calendar(creator="-//LPU Reserve//EduRev P20//EN")
        calendar.events.add(event)
        response = HttpResponse(calendar.serialize(), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{booking.reference}.ics"'
        return response


@extend_schema(tags=["bookings"])
class SeriesViewSet(viewsets.GenericViewSet):
    """Recurring bookings (faculty and staff)."""

    serializer_class = SeriesRequestSerializer
    permission_classes = [IsAuthenticated, HasCap("book_recurring")]

    @extend_schema(
        summary="Dry-run a recurring pattern: which dates can be booked, and why not",
        request=SeriesRequestSerializer,
        responses={200: SeriesPreviewSerializer, **error_responses(400, 403)},
    )
    @action(detail=False, methods=["post"])
    def preview(self, request):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        occurrences = services.expand_occurrences(**body.occurrence_kwargs())
        plans = services.preview_series(
            requester=request.user,
            resource=v["resource"],
            occurrences=occurrences,
            attendees=v["attendees"],
            booked_for=v.get("booked_for"),
        )
        payload = {"total": len(plans), "bookable": sum(1 for p in plans if p.ok), "occurrences": plans}
        return Response(SeriesPreviewSerializer(payload).data)

    @extend_schema(
        summary="Create a recurring booking; dates that can't be booked are skipped with a reason",
        request=SeriesRequestSerializer,
        responses={201: SeriesResultSerializer, **error_responses(400, 403, 422)},
    )
    def create(self, request):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        resource = v["resource"]
        series, created, skipped = services.create_series(
            requester=request.user,
            resource=resource,
            title=v["title"] or f"{resource.name} (recurring)",
            attendees=v["attendees"],
            group_label=v["group_label"],
            booked_for=v.get("booked_for"),
            notes=v["notes"],
            request=request,
            **body.occurrence_kwargs(),
        )
        payload = {"series": series, "created": created, "skipped": skipped}
        return Response(SeriesResultSerializer(payload).data, status=status.HTTP_201_CREATED)
