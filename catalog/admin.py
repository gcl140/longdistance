from django.contrib import admin
from django.utils import timezone

from .models import Movie, MovieRequest


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "year", "rating", "is_playable", "added_by", "created_at")
    list_filter = ("transcode_status",)
    search_fields = ("title", "year", "tmdb_id")
    readonly_fields = ("created_at", "tmdb_data")


@admin.register(MovieRequest)
class MovieRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title", "year", "status", "vote_count", "requester", "created_at",
        "fulfilled_movie",
    )
    list_filter = ("status",)
    search_fields = ("title", "tmdb_id", "requester__email")
    readonly_fields = ("vote_count", "voters", "created_at", "tmdb_id")
    actions = ("mark_approved", "mark_rejected", "mark_fulfilled")

    @admin.action(description="Approve selected requests")
    def mark_approved(self, request, queryset):
        queryset.update(status="approved", reviewed_at=timezone.now())

    @admin.action(description="Reject selected requests")
    def mark_rejected(self, request, queryset):
        queryset.update(status="rejected", reviewed_at=timezone.now())

    @admin.action(description="Mark fulfilled (you've uploaded the file)")
    def mark_fulfilled(self, request, queryset):
        queryset.update(status="fulfilled", reviewed_at=timezone.now())
