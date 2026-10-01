from django.urls import path

from . import views

app_name = "checkins"

urlpatterns = [
    path("scan/", views.scan, name="scan"),
    path("c/<str:token>/", views.pass_landing, name="pass"),
    path("here/<str:code>/", views.here, name="here"),
    path("b/<str:reference>/check-in/", views.check_in, name="check_in"),
    path("b/<str:reference>/check-out/", views.check_out, name="check_out"),
]
