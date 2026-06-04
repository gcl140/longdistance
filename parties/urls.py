from django.urls import path

from . import views

app_name = "parties"

urlpatterns = [
    path("", views.my_parties, name="my_parties"),
    path("create/", views.create_party, name="create"),
    path("join/", views.join_party, name="join"),
    path("room/<str:code>/", views.room, name="room"),
    # JSON polling endpoints
    path("room/<str:code>/state/", views.session_state, name="session_state"),
    path("room/<str:code>/update/", views.session_update, name="session_update"),
    path("room/<str:code>/messages/", views.messages_json, name="messages"),
    path("room/<str:code>/send/", views.send_message, name="send_message"),
    # actions
    path("room/<str:code>/leave/", views.leave_party, name="leave"),
    path("room/<str:code>/end/", views.end_party, name="end"),
    path("room/<str:code>/invite/", views.invite_to_party, name="invite"),
]
