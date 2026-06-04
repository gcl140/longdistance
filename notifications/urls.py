from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("feed/", views.feed, name="feed"),
    path("unread/", views.unread_count, name="unread_count"),
    path("presence/", views.friends_presence, name="presence"),
    path("<int:note_id>/read/", views.mark_read, name="mark_read"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
]
