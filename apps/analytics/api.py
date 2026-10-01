"""M9 — Utilisation analytics API. Department heads see their department; campus analysts see everything."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Department
from apps.accounts.permissions import has_cap
from apps.catalogue.models import ResourceType
from apps.core.api import HasCap, error_body, error_responses
from apps.core.errors import NotPermitted

from . import services
from .serializers import UtilisationQuerySerializer, UtilisationReportSerializer


@extend_schema(tags=["analytics"])
class UtilisationView(APIView):
    permission_classes = [IsAuthenticated, HasCap("view_department_analytics")]

    def _department(self, request, code):
        user = request.user
        if has_cap(user, "view_campus_analytics"):
            if not code:
                return None
            return get_object_or_404(Department, institution_id=user.institution_id, code=code)
        # Department-scoped analysts: always their own department, never another one.
        if user.department_id is None:
            raise NotPermitted("Your account isn't linked to a department, so there is no data to show.")
        if code and code != user.department.code:
            raise NotPermitted("You can only see your own department's utilisation.")
        return user.department

    @extend_schema(
        summary="Utilisation grouped by type, resource, department or building",
        parameters=[UtilisationQuerySerializer],
        responses={200: UtilisationReportSerializer, **error_responses(400, 403, 503)},
    )
    def get(self, request):
        params = UtilisationQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        q = params.validated_data
        department = self._department(request, q.get("department"))
        rtype = (
            get_object_or_404(ResourceType, institution_id=request.user.institution_id, code=q["type"])
            if q.get("type")
            else None
        )
        scope = {
            "institution_id": request.user.institution_id,
            "start": q["start"],
            "end": q["end"],
            "department_id": department.pk if department else None,
            "resource_type_id": rtype.pk if rtype else None,
        }
        try:
            rows = services.utilisation_by(q["by"], **scope)
            overview = services.overview(**scope)
        except NotImplementedError:
            return Response(
                error_body("analytics_unavailable", "Utilisation analytics are not available yet. Try again later."),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        payload = {
            "start": q["start"],
            "end": q["end"],
            "by": q["by"],
            "scope": {"department": department.code if department else None, "type": rtype.code if rtype else None},
            "overview": overview,
            "rows": rows,
        }
        return Response(UtilisationReportSerializer(payload).data)
