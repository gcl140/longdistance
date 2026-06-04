"""ASGI config for longdistance — HTTP + WebSocket (Channels)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'longdistance.settings')

# Initialise Django ASGI app early so apps are loaded before importing consumers.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from notifications.routing import websocket_urlpatterns as notification_ws  # noqa: E402
from parties.routing import websocket_urlpatterns as party_ws  # noqa: E402

websocket_urlpatterns = party_ws + notification_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})

# This module is imported only when serving ASGI (Daphne), never by management
# commands like migrate/collectstatic — so it's a safe place to recover any
# transcodes that a previous restart interrupted, off the main thread.
import threading  # noqa: E402


def _resume_transcodes():
    try:
        from catalog.transcode import resume_stuck
        resume_stuck()
    except Exception as e:  # never let startup recovery crash the server
        print(f"[asgi] transcode resume failed: {e}")


threading.Thread(target=_resume_transcodes, daemon=True).start()
