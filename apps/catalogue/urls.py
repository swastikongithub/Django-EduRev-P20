from django.urls import path

from . import views

app_name = "catalogue"

urlpatterns = [
    path("r/<slug:slug>/", views.detail, name="detail"),
]
