from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/demo/", views.demo_login, name="demo_login"),
    path("logout/", views.logout_view, name="logout"),
    path("me/", views.me, name="me"),
]
