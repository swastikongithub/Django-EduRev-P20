from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.catalogue.models import Resource
from apps.core.errors import DomainError

from . import services
from .models import Severity


@login_required
@require_POST
def report(request, slug):
    """Anyone who finds something broken can say so — that's how custodians hear about it first."""
    resource = get_object_or_404(Resource, institution_id=request.user.institution_id, slug=slug)
    summary = request.POST.get("summary", "").strip()
    severity = request.POST.get("severity", Severity.HIGH)
    if severity not in Severity.values:
        severity = Severity.HIGH
    if not summary:
        messages.error(request, "Describe what's wrong in a few words.")
        return redirect(resource.get_absolute_url())
    try:
        services.report_breakdown(resource, request.user, summary=summary, details=request.POST.get("details", "")[:2000],
                                  severity=severity, request=request)
        messages.success(request, "Thanks — the custodian has been told." + (" It's marked out of service until checked." if severity == Severity.CRITICAL else ""))
    except DomainError as exc:
        messages.error(request, exc.message)
    return redirect(resource.get_absolute_url())
