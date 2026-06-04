import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from . import presence
from .services import user_group


class NotificationConsumer(AsyncWebsocketConsumer):
    """One connection per open tab for a logged-in user.

    Joins the per-user group `user_<id>` so `push_notification` can reach every
    open tab. Connecting/disconnecting also drives presence and broadcasts
    online/offline to the user's friends (only friends ever learn presence).
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.group = user_group(self.user.id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # First tab → this user just came online.
        count = await database_sync_to_async(presence.mark_online)(self.user.id)
        if count == 1:
            await self._broadcast_presence(True)

    async def disconnect(self, code):
        if not hasattr(self, "group"):
            return
        await self.channel_layer.group_discard(self.group, self.channel_name)
        count = await database_sync_to_async(presence.mark_offline)(self.user.id)
        if count == 0:
            await self._broadcast_presence(False)

    async def receive(self, text_data=None, bytes_data=None):
        """Client → server: only a lightweight heartbeat / mark-read ping."""
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return
        if data.get("type") == "mark_read":
            await database_sync_to_async(self._mark_read)(data.get("id"))

    # ---- group event handlers (server → this client) ----

    async def notify_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "notify",
            "notification": event["notification"],
        }))

    async def presence_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "presence",
            "user_id": event["user_id"],
            "online": event["online"],
        }))

    # ---- helpers ----

    async def _broadcast_presence(self, online):
        friend_ids = await database_sync_to_async(self._friend_ids)()
        for fid in friend_ids:
            await self.channel_layer.group_send(
                user_group(fid),
                {"type": "presence.message", "user_id": self.user.id, "online": online},
            )

    def _friend_ids(self):
        # Users who have me in their contacts — i.e. people allowed to see me.
        from friends.models import Contact
        return list(
            Contact.objects.filter(friend=self.user, is_blocked=False)
            .values_list("user_id", flat=True)
        )

    def _mark_read(self, note_id):
        if not note_id:
            return
        from .models import Notification
        Notification.objects.filter(id=note_id, recipient=self.user).update(is_read=True)
