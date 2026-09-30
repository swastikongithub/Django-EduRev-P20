from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


@login_required
def detail(request, reference):  # replaced by the booking pass UI
    return HttpResponse(reference)
