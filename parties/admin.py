from django.contrib import admin

from .models import (
    PartyInvite,
    PartyMessage,
    VideoSession,
    WatchParty,
    WatchPartyMember,
)


class WatchPartyMemberInline(admin.TabularInline):
    model = WatchPartyMember
    extra = 0


class VideoSessionInline(admin.StackedInline):
    model = VideoSession
    extra = 0


@admin.register(WatchParty)
class WatchPartyAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "access_code", "is_private", "scheduled_for", "is_active", "created_at")
    list_filter = ("is_private",)
    search_fields = ("name", "access_code", "host__email")
    readonly_fields = ("access_code", "created_at")
    inlines = [VideoSessionInline, WatchPartyMemberInline]


@admin.register(WatchPartyMember)
class WatchPartyMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "party", "is_moderator", "joined_at", "last_seen")
    list_filter = ("is_moderator",)
    search_fields = ("user__email", "party__name")


@admin.register(VideoSession)
class VideoSessionAdmin(admin.ModelAdmin):
    list_display = ("party", "title", "is_playing", "current_position", "duration", "updated_at")
    search_fields = ("party__name", "title")


@admin.register(PartyInvite)
class PartyInviteAdmin(admin.ModelAdmin):
    list_display = ("party", "sender", "recipient", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("party__name", "sender__email", "recipient__email")


@admin.register(PartyMessage)
class PartyMessageAdmin(admin.ModelAdmin):
    list_display = ("party", "sender", "message", "created_at")
    search_fields = ("party__name", "sender__email", "message")
