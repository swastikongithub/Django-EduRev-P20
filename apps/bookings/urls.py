from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("r/<slug:slug>/book/", views.create, name="create"),
    path("b/<str:reference>/", views.detail, name="detail"),
    path("b/<str:reference>/cancel/", views.cancel, name="cancel"),
    path("b/<str:reference>/calendar.ics", views.ics, name="ics"),
    path("bookings/", views.mine, name="mine"),
    path("bookings/repeat/", views.series_new, name="series_new"),
    path("calendar/", views.calendar, name="calendar"),
    path("feed/<uuid:token>.ics", views.feed, name="feed"),
]
