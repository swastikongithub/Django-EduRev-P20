"""Branded error pages — no raw Django errors in front of students."""

from django.shortcuts import render


def forbidden(request, exception=None):
    return render(request, "errors/error.html", {"code": 403, "title": "That's not open to your role",
                  "message": "Your account doesn't have access to this page. If you think it should, ask your department office."}, status=403)


def not_found(request, exception=None):
    return render(request, "errors/error.html", {"code": 404, "title": "We couldn't find that",
                  "message": "The link may be old, or the booking may belong to someone else."}, status=404)


def server_error(request):
    return render(request, "errors/error.html", {"code": 500, "title": "Something broke on our side",
                  "message": "It's been logged. Try again in a moment; your existing bookings are safe."}, status=500)
