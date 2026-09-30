from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("b/<str:reference>/", views.detail, name="detail"),
]
