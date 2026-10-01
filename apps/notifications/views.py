from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notification
from .services import mark_all_read


@login_required
def inbox(request):
    qs = Notification.objects.filter(user=request.user)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    unread_ids = {n.pk for n in page.object_list if n.read_at is None}
    resp = render(request, "notifications/inbox.html", {"page": page, "unread_ids": unread_ids})
    mark_all_read(request.user)  # opening the inbox reads it; this page still highlights what was new
    return resp


@login_required
@require_POST
def read_all(request):
    mark_all_read(request.user)
    return redirect("notifications:inbox")
