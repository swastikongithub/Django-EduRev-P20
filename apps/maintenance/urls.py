from django.urls import path

from . import views

app_name = "maintenance"

urlpatterns = [
    path("r/<slug:slug>/report/", views.report, name="report"),
]
