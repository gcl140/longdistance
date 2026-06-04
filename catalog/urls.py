from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("search/", views.search, name="search"),
    path("trending/", views.trending, name="trending"),
    path("request/", views.request_movie, name="request"),
    path("request-state/", views.request_state, name="request_state"),
    path("quota/", views.quota_status, name="quota"),
    path("requests/", views.my_requests, name="my_requests"),
    path("requests/<int:req_id>/<str:action>/", views.request_set_status, name="request_action"),
    path("library.json", views.library_json, name="library_json"),
    path("", views.library, name="library"),
    path("upload/", views.upload_movie, name="upload"),
    path("<int:movie_id>/watch/", views.watch_movie, name="watch"),
    path("<int:movie_id>/detail.json", views.movie_detail, name="detail"),
    path("tmdb/<int:tmdb_id>/detail.json", views.tmdb_detail, name="tmdb_detail"),
    path("<int:movie_id>/status/", views.movie_status, name="status"),
    path("<int:movie_id>/delete/", views.delete_movie, name="delete"),
]
