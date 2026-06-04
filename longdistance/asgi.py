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
