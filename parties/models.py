import secrets

from django.conf import settings
from django.db import models


def generate_access_code():
    """Short, URL-safe, human-shareable room code (e.g. 'a1B2c3D4')."""
    return secrets.token_urlsafe(6)[:8]


class WatchParty(models.Model):
    """A room where members watch a video together in sync."""

    name = models.CharField(max_length=255)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_parties",
    )

    is_private = models.BooleanField(default=True)
    access_code = models.CharField(
        max_length=20, unique=True, default=generate_access_code, db_index=True
    )

    # Optional movie-night schedule. Null = start now / unscheduled.
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Watch parties"

    @property
    def is_active(self):
        return self.ended_at is None

    def __str__(self):
        return f"{self.name} ({self.access_code})"


class WatchPartyMember(models.Model):
    """Membership of a user in a party. Not stored on WatchParty directly."""

    party = models.ForeignKey(
        WatchParty, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="party_memberships",
    )

    is_moderator = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["party", "user"], name="unique_party_member"
            )
        ]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.party.name}"


class VideoSession(models.Model):
    """Authoritative playback state for a party's current video.

    `video_url` points at the self-hosted media API (home-PC server). One live
    session per party; updated by the host and broadcast over WebSockets later.
    """

    party = models.OneToOneField(
        WatchParty, on_delete=models.CASCADE, related_name="session"
    )

    video_url = models.URLField(blank=True)
    subtitle_url = models.URLField(blank=True)
    poster_url = models.URLField(blank=True)
    title = models.CharField(max_length=255, blank=True)

    duration = models.FloatField(default=0)            # seconds
    current_position = models.FloatField(default=0)    # seconds
    is_playing = models.BooleanField(default=False)
    playback_rate = models.FloatField(default=1.0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session for {self.party.name}"


class PartyInvite(models.Model):
    """An invitation to join a specific party."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

    party = models.ForeignKey(
        WatchParty, on_delete=models.CASCADE, related_name="invites"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invites",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_invites",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["party", "recipient"], name="unique_party_invite"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender} invited {self.recipient} to {self.party.name}"


class PartyMessage(models.Model):
    """Persisted chat message in a party room."""

    party = models.ForeignKey(
        WatchParty, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="party_messages",
    )

    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender}: {self.message[:40]}"
