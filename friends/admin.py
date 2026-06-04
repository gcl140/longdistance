from django.contrib import admin

from .models import Contact, FriendRequest


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("user", "friend", "nickname", "is_favorite", "is_blocked", "created_at")
    list_filter = ("is_favorite", "is_blocked", "is_muted")
    search_fields = ("user__email", "friend__email", "nickname")


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "status", "created_at", "responded_at")
    list_filter = ("status",)
    search_fields = ("from_user__email", "to_user__email")
