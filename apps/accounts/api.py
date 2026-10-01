"""The caller's own profile: role, capabilities, quota usage and any active booking restriction."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.checkins.services import active_restriction
from apps.notifications.services import unread_count
from apps.rules.services import quota_usage

from .serializers import MeSerializer


@extend_schema(tags=["accounts"])
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="My profile, capabilities, quota usage and restriction", responses={200: MeSerializer})
    def get(self, request):
        user = request.user
        user.quota_usage = quota_usage(user)
        user.active_restriction = active_restriction(user)
        user.unread_notifications = unread_count(user)
        return Response(MeSerializer(user).data)
