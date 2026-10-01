"""M1 — Resource catalogue API: search, filter, detail and availability."""

from datetime import timedelta

import django_filters
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db.models import Case, Q, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import exceptions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.bookings import availability
from apps.bookings.models import BookingSlot
from apps.core.api import StandardPagination, error_responses
from apps.core.timeutil import trange

from .models import Feature, Resource, ResourceStatus
from .serializers import (
    AvailabilityQuerySerializer,
    AvailabilitySerializer,
    ResourceDetailSerializer,
    ResourceSerializer,
)

ID_OR_SLUG = OpenApiParameter("id_or_slug", OpenApiTypes.STR, OpenApiParameter.PATH, description="Resource id or slug")


def institution_resources(user):
    return Resource.objects.filter(institution_id=user.institution_id).exclude(status=ResourceStatus.RETIRED)


def get_resource(user, key: str) -> Resource:
    """Look a resource up by numeric id or slug, within the user's institution."""
    qs = institution_resources(user).select_related("type", "building", "department")
    if key.isdigit():
        found = qs.filter(pk=int(key)).first()
        if found:
            return found
    return get_object_or_404(qs, slug=key)


class ResourceFilter(django_filters.FilterSet):
    type = django_filters.CharFilter(method="filter_type", help_text="Resource type code(s), comma-separated")
    category = django_filters.CharFilter(field_name="type__category", help_text="space, lab, equipment, ...")
    building = django_filters.CharFilter(field_name="building__code", help_text="Building code, e.g. 34")
    department = django_filters.CharFilter(field_name="department__code", help_text="Owning department code")
    min_capacity = django_filters.NumberFilter(field_name="capacity", lookup_expr="gte", min_value=1)
    features = django_filters.CharFilter(
        method="filter_features", help_text="Comma-separated feature ids or names; the resource must have all"
    )
    status = django_filters.ChoiceFilter(choices=ResourceStatus.choices)
    q = django_filters.CharFilter(method="filter_q", help_text="Full-text + fuzzy search on name, code, features")
    free_from = django_filters.IsoDateTimeFilter(method="noop", help_text="With free_to: only resources free then")
    free_to = django_filters.IsoDateTimeFilter(method="noop", help_text="End of the free window")

    class Meta:
        model = Resource
        fields = []

    def noop(self, queryset, name, value):
        return queryset  # applied together in filter_queryset

    def filter_type(self, queryset, name, value):
        codes = [c.strip() for c in value.split(",") if c.strip()]
        return queryset.filter(type__code__in=codes) if codes else queryset

    def filter_features(self, queryset, name, value):
        for token in (t.strip() for t in value.split(",")):
            if not token:
                continue
            match = (
                Feature.objects.filter(pk=int(token)) if token.isdigit() else Feature.objects.filter(name__iexact=token)
            )
            queryset = queryset.filter(features__in=match)
        return queryset.distinct()

    def filter_q(self, queryset, name, value):
        value = value.strip()[:100]
        if not value:
            return queryset
        vector = (
            SearchVector("name", weight="A", config="simple")
            + SearchVector("code", weight="A", config="simple")
            + SearchVector("tagline", "description", weight="B", config="simple")
        )
        query = SearchQuery(value, search_type="websearch", config="simple")
        feature_hits = Feature.objects.filter(Q(name__icontains=value) | Q(keywords__icontains=value)).values("pk")
        return (
            queryset.annotate(
                exact=Case(When(Q(code__iexact=value) | Q(name__iexact=value), then=1), default=0),
                document=vector,
                rank=SearchRank(vector, query),
                similarity=TrigramSimilarity("name", value),
            )
            .filter(
                Q(document=query)
                | Q(search_vector=query)
                | Q(similarity__gt=0.2)
                | Q(code__icontains=value)
                | Q(building__name__icontains=value)
                | Q(features__in=feature_hits)
            )
            .distinct()
            .order_by("-exact", "-rank", "-similarity", "code")
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        start, end = self.form.cleaned_data.get("free_from"), self.form.cleaned_data.get("free_to")
        if start is None and end is None:
            return queryset
        if start is None or end is None:
            raise exceptions.ValidationError({"free_from": ["free_from and free_to must be given together."]})
        if end <= start:
            raise exceptions.ValidationError({"free_to": ["free_to must be after free_from."]})
        if end - start > timedelta(days=7):
            raise exceptions.ValidationError({"free_to": ["The free window can span at most 7 days."]})
        busy = BookingSlot.objects.filter(period__overlap=trange(start, end)).values("resource_id")
        return queryset.filter(status=ResourceStatus.ACTIVE, is_bookable=True).exclude(pk__in=busy)


@extend_schema(tags=["catalogue"])
@extend_schema_view(
    list=extend_schema(summary="Search and filter resources"),
    retrieve=extend_schema(
        summary="Resource detail", parameters=[ID_OR_SLUG], responses={200: ResourceDetailSerializer}
    ),
)
class ResourceViewSet(viewsets.ReadOnlyModelViewSet):
    """Bookable resources of the caller's institution (retired resources are hidden)."""

    serializer_class = ResourceSerializer
    filterset_class = ResourceFilter
    pagination_class = StandardPagination
    lookup_url_kwarg = "id_or_slug"
    lookup_value_regex = "[^/]+"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Resource.objects.none()
        return (
            institution_resources(self.request.user)
            .select_related("type", "building", "department")
            .prefetch_related("features")
        )

    def get_serializer_class(self):
        return ResourceDetailSerializer if self.action == "retrieve" else ResourceSerializer

    def get_object(self):
        resource = get_resource(self.request.user, self.kwargs[self.lookup_url_kwarg])
        self.check_object_permissions(self.request, resource)
        return resource

    @extend_schema(
        summary="Availability grid with a reason for every cell",
        parameters=[ID_OR_SLUG, AvailabilityQuerySerializer],
        responses={200: AvailabilitySerializer, **error_responses(400, 404)},
    )
    @action(detail=True, methods=["get"])
    def availability(self, request, id_or_slug=None):
        resource = self.get_object()
        params = AvailabilityQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        first = params.validated_data.get("date") or timezone.localdate()
        days = [first + timedelta(days=i) for i in range(params.validated_data["days"])]
        schedules = availability.schedule(resource, days, request.user)
        return Response(AvailabilitySerializer({"resource": resource, "days": schedules}).data)
