"""The single entry point for creating + delivering a notification.

Anything that wants to notify a user calls `push_notification`. It writes the
`Notification` row (durable history for the bell) and pushes it live over the
recipient's WebSocket group (`user_<id>`) so an open client dings immediately.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notification


def user_group(uid):
    return f"user_{uid}"


def push_notification(recipient, kind, title, body="", actor=None, url="", data=None):
    """Create a Notification for `recipient` and push it to their live sockets.

    Returns the saved Notification. Safe to call from sync view code.
    """
    note = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        kind=kind,
        title=title,
        body=body,
        url=url,
        data=data or {},
    )
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            user_group(recipient.id),
            {"type": "notify.message", "notification": note.as_dict()},
        )
    return note


def push_presence(uid, target_uids, online):
    """Tell each user in `target_uids` that user `uid` went online/offline."""
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {"type": "presence.message", "user_id": uid, "online": online}
    for tid in target_uids:
        async_to_sync(layer.group_send)(user_group(tid), payload)
