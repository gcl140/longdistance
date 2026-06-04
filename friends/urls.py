from django.urls import path

from . import views

app_name = "friends"

urlpatterns = [
    path("", views.friends_list, name="list"),
    path("search/", views.search, name="search"),
    path("request/", views.send_request, name="request"),
    # Back-compat alias: the old "add by email" form name.
    path("add/", views.send_request, name="add"),
    path("request/<int:request_id>/<str:action>/", views.respond_request, name="respond_request"),
    path("<int:contact_id>/remove/", views.remove_friend, name="remove"),
    path("<int:contact_id>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("invite/<int:invite_id>/<str:action>/", views.respond_invite, name="respond_invite"),
]
