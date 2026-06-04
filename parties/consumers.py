import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import PartyMessage, VideoSession, WatchParty, WatchPartyMember


class PartyConsumer(AsyncWebsocketConsumer):
    """One connection per (user, party). Carries chat, playback sync,
    presence, and WebRTC signaling — all tiny JSON control messages.
    """

    async def connect(self):
        self.code = self.scope["url_route"]["kwargs"]["code"]
        self.group = f"party_{self.code}"
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.party = await self._get_party(self.code)
        if not self.party or not await self._is_member(self.party, self.user):
            await self.close()
            return

        self.peer_id = self.channel_name  # unique per connection (WebRTC id)
        self.can_control = await self._can_control(self.party, self.user)
        self.display = self.user.get_full_name().strip() or self.user.email

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # Tell this client its own peer id + control rights.
        await self.send(text_data=json.dumps({
            "type": "welcome",
            "peer_id": self.peer_id,
            "can_control": self.can_control,
        }))

        await self.channel_layer.group_send(self.group, {
            "type": "presence",
            "event": "join",
            "peer_id": self.peer_id,
            "user_id": self.user.id,
            "display": self.display,
        })

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_send(self.group, {
                "type": "presence",
                "event": "leave",
                "peer_id": self.peer_id,
                "user_id": self.user.id,
                "display": self.display,
            })
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return
        kind = data.get("type")

        if kind == "chat":
            text = (data.get("message") or "").strip()[:2000]
            if not text:
                return
            msg = await self._save_message(self.party, self.user, text)
            await self.channel_layer.group_send(self.group, {
                "type": "chat_message",
                "id": msg.id,
                "sender_id": self.user.id,
                "sender": self.display,
                "message": text,
                "at": msg.created_at.strftime("%H:%M"),
            })

        elif kind == "sync":
            if not self.can_control:
                return
            await self._save_session(self.party, data)
            await self.channel_layer.group_send(self.group, {
                "type": "sync_state",
                "origin": self.peer_id,
                "is_playing": data.get("is_playing"),
                "position": data.get("position"),
                "video_url": data.get("video_url"),
                "subtitle": data.get("subtitle"),
                "title": data.get("title"),
            })

        elif kind == "webrtc":
            # Relay signaling (offer/answer/ICE/join) to the group; clients filter by `to`.
            await self.channel_layer.group_send(self.group, {
                "type": "webrtc_signal",
                "from": self.peer_id,
                "from_user": self.display,
                "from_user_id": self.user.id,  # stable id so tiles dedupe per user
                "to": data.get("to"),          # None = broadcast (call announce)
                "signal": data.get("signal"),
                "action": data.get("action"),  # 'join' | 'leave' | 'offer' | 'answer' | 'ice'
            })

    # ---- group event handlers ----
    async def chat_message(self, e):
        await self.send(text_data=json.dumps({
            "type": "chat",
            "id": e["id"],
            "sender_id": e["sender_id"],
            "sender": e["sender"],
            "is_me": e["sender_id"] == self.user.id,
            "message": e["message"],
            "at": e["at"],
        }))

    async def sync_state(self, e):
        if e["origin"] == self.peer_id:
            return  # don't echo to the controller
        await self.send(text_data=json.dumps({
            "type": "sync",
            "is_playing": e["is_playing"],
            "position": e["position"],
            "video_url": e["video_url"],
            "subtitle": e.get("subtitle"),
            "title": e["title"],
        }))

    async def presence(self, e):
        if e["peer_id"] == self.peer_id and e["event"] == "join":
            return  # don't tell yourself you joined
        await self.send(text_data=json.dumps({
            "type": "presence",
            "event": e["event"],
            "peer_id": e["peer_id"],
            "user_id": e["user_id"],
            "display": e["display"],
        }))

    async def webrtc_signal(self, e):
        if e["from"] == self.peer_id:
            return  # ignore own signals
        if e["to"] and e["to"] != self.peer_id:
            return  # targeted at someone else
        await self.send(text_data=json.dumps({
            "type": "webrtc",
            "from": e["from"],
            "from_user": e["from_user"],
            "from_user_id": e.get("from_user_id"),
            "action": e["action"],
            "signal": e["signal"],
        }))

    # ---- DB helpers ----
    @database_sync_to_async
    def _get_party(self, code):
        return WatchParty.objects.filter(access_code=code, ended_at__isnull=True).first()

    @database_sync_to_async
    def _is_member(self, party, user):
        return party.host_id == user.id or WatchPartyMember.objects.filter(
            party=party, user=user
        ).exists()

    @database_sync_to_async
    def _can_control(self, party, user):
        if party.host_id == user.id:
            return True
        m = WatchPartyMember.objects.filter(party=party, user=user).first()
        return bool(m and m.is_moderator)

    @database_sync_to_async
    def _save_message(self, party, user, text):
        return PartyMessage.objects.create(party=party, sender=user, message=text)

    @database_sync_to_async
    def _save_session(self, party, data):
        s, _ = VideoSession.objects.get_or_create(party=party)
        if data.get("is_playing") is not None:
            s.is_playing = bool(data["is_playing"])
        if data.get("position") is not None:
            s.current_position = float(data["position"])
        if data.get("video_url") is not None:
            s.video_url = data["video_url"] or ""
        if data.get("subtitle") is not None:
            s.subtitle_url = data["subtitle"] or ""
        if data.get("poster") is not None:
            s.poster_url = data["poster"] or ""
        if data.get("title") is not None:
            s.title = data["title"] or ""
        s.save()
        return s
