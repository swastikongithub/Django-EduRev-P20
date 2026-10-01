from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/demo/", views.demo_login, name="demo_login"),
    path("login/verify/", views.mfa_view, name="mfa"),
    path("logout/", views.logout_view, name="logout"),
    path("me/", views.me, name="me"),
    path("me/export/", views.export_my_data, name="export"),
]
