from django.urls import path

from . import views

app_name = "schedule"

urlpatterns = [
    path("", views.calendar_view, name="calendar"),
    path("event/<str:code>.ics", views.ics_event, name="ics_event"),
    path("feed/<str:token>.ics", views.ics_feed, name="feed"),
]
