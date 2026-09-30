from django.urls import path

from . import views

app_name = "catalogue"

urlpatterns = [
    path("find/", views.find, name="find"),
    path("r/<slug:slug>/", views.detail, name="detail"),
    path("r/<slug:slug>/save/", views.toggle_save, name="save"),
]
