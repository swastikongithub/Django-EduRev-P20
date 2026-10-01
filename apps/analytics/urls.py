from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("insights/", views.dashboard, name="dashboard"),
    path("insights/export/<slug:report>.csv", views.export, name="export"),
]
