"""
Shared REST API plumbing: the error envelope, capability permissions and pagination.

Every error the API returns has one shape, whether it came from a domain service,
a serializer or DRF itself:

    {"error": {"code": "conflict", "message": "Already booked 10:00–11:00.", "detail": {...}}}

Domain errors keep their HTTP status (NotPermitted 403, SlotUnavailable 409,
BookingRejected 422, InvalidTransition 409).
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.accounts.permissions import has_cap
from apps.core.errors import DomainError


def error_body(code: str, message: str, detail=None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def _first_message(data, prefix: str = "") -> str:
    """The first human sentence in a (possibly nested) DRF validation payload."""
    if isinstance(data, dict):
        for key, value in data.items():
            label = "" if key in ("non_field_errors", "detail") else f"{prefix}{key}"
            msg = _first_message(value, f"{label}." if label else prefix)
            if msg:
                return msg
        return ""
    if isinstance(data, list):
        for i, value in enumerate(data):
            nested = isinstance(value, dict | list)
            msg = _first_message(value, f"{prefix}{i}." if nested else prefix)
            if msg:
                return msg
        return ""
    field = prefix.rstrip(".")
    return f"{field}: {data}" if field else str(data)


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response(error_body(exc.code, exc.message, exc.detail), status=exc.status)

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django's 500 handling

    data = response.data
    if isinstance(exc, exceptions.ValidationError):
        detail = data if isinstance(data, dict) else {"non_field_errors": data}
        message = _first_message(detail) or "Some of the submitted values are not valid."
        response.data = error_body("invalid", message, detail)
        return response

    codes = exc.get_codes() if isinstance(exc, exceptions.APIException) else None
    code = codes if isinstance(codes, str) else "error"
    if isinstance(data, dict):
        message = str(data.get("detail", "")) or code
        detail = {k: v for k, v in data.items() if k != "detail"}
    else:
        message, detail = str(data), {}
    response.data = error_body(code, message, detail)
    return response


# ── Schema helpers ──────────────────────────────────────────────────────────


class ErrorSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Machine-readable code, e.g. conflict, quota, forbidden, invalid")
    message = serializers.CharField(help_text="A sentence the user can act on")
    detail = serializers.DictField(help_text="Structured context (conflicts, field errors...)")


class ErrorEnvelopeSerializer(serializers.Serializer):
    error = ErrorSerializer()


def error_responses(*statuses: int) -> dict:
    return dict.fromkeys(statuses, ErrorEnvelopeSerializer)


# ── Permissions ─────────────────────────────────────────────────────────────


def HasCap(*codenames: str, any_of: bool = False) -> type[BasePermission]:  # noqa: N802 - reads like a class
    """
    Permission class factory: `permission_classes = [IsAuthenticated, HasCap("approve_bookings")]`.
    With several codenames the user needs all of them (or any, with any_of=True).
    """

    class _HasCap(BasePermission):
        message = "Your role doesn't allow this."

        def has_permission(self, request, view):
            check = any if any_of else all
            return check(has_cap(request.user, c) for c in codenames)

    _HasCap.__name__ = "HasCap_" + "_".join(codenames)
    _HasCap.__qualname__ = _HasCap.__name__
    return _HasCap


# ── Pagination ──────────────────────────────────────────────────────────────


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
