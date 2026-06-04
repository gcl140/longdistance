from django.conf import settings
from django.db import models


class Notification(models.Model):
    """A single in-app notification for one recipient.

    Notifications are created + delivered exclusively through
    `notifications.services.push_notification`, which writes this row and then
    pushes it over the recipient's WebSocket group (`user_<id>`).

    `kind` decides how the bell UI handles a click:
      - friend_request  → opens an approve/reject modal (uses data.friend_request_id)
      - friend_accepted → navigates to the Friends page (url)
      - party_invite    → navigates to the room (url; data has invite_id + code)
      - generic         → navigates to url if set
    `data` carries the ids the UI needs without extra round-trips.
    """

    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPTED = "friend_accepted"
    PARTY_INVITE = "party_invite"
    GENERIC = "generic"
    KIND_CHOICES = [
        (FRIEND_REQUEST, "Friend request"),
        (FRIEND_ACCEPTED, "Friend request accepted"),
        (PARTY_INVITE, "Party invite"),
        (GENERIC, "Generic"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=GENERIC)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    data = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} → {self.recipient} ({'read' if self.is_read else 'unread'})"

    def as_dict(self):
        """Serialised shape used by both the WebSocket push and the JSON feed."""
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "data": self.data or {},
            "is_read": self.is_read,
            "actor": (
                (self.actor.get_full_name().strip() or self.actor.email)
                if self.actor_id
                else ""
            ),
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }
