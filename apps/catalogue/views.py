from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


@login_required
def detail(request, slug):  # replaced by the resource page UI
    return HttpResponse(slug)
