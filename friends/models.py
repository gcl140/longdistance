from django.conf import settings
from django.db import models


class Contact(models.Model):
    """A directed friendship edge: `user` has `friend` in their contacts.

    A mutual friendship is represented by two rows (one each direction), which
    keeps per-side data (nickname, favorite, blocked) independent.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    friend = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friend_of",
    )

    nickname = models.CharField(max_length=100, blank=True)
    is_favorite = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "friend"], name="unique_contact_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(user=models.F("friend")),
                name="contact_not_self",
            ),
        ]
        ordering = ["-is_favorite", "nickname"]

    def __str__(self):
        return f"{self.user} → {self.friend}"


class FriendRequest(models.Model):
    """A pending ask from `from_user` to befriend `to_user`.

    Accepting creates the two symmetric `Contact` rows (see
    `friends.views.respond_request`). One pending request per ordered pair.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_friend_requests",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"], name="unique_friend_request_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="friend_request_not_self",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.from_user} → {self.to_user} ({self.status})"
