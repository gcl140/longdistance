"""Online/offline presence, backed by Django's cache.

A user is "online" while they hold at least one open notification WebSocket
(see `NotificationConsumer`). We keep a per-user connection counter so multiple
tabs don't prematurely flip someone offline.

Dev note: the default cache is `LocMemCache`, which is per-process — fine for a
single `runserver`/daphne process. In production with multiple workers this must
be a SHARED cache (point Django's CACHES at the same Redis used by CHANNEL_LAYERS
via REDIS_URL), otherwise presence will be wrong across processes.
"""

from django.core.cache import cache

_PREFIX = "presence:"
# Counters never expire on their own; connect/disconnect keep them balanced.
# A long TTL is a safety net against leaked counts if a disconnect is missed.
_TTL = 60 * 60 * 12


def _key(uid):
    return f"{_PREFIX}{uid}"


def mark_online(uid):
    """Register one open connection for this user. Returns the new count."""
    key = _key(uid)
    count = (cache.get(key) or 0) + 1
    cache.set(key, count, _TTL)
    return count


def mark_offline(uid):
    """Drop one connection; clears the key when the last tab closes."""
    key = _key(uid)
    count = (cache.get(key) or 0) - 1
    if count <= 0:
        cache.delete(key)
        return 0
    cache.set(key, count, _TTL)
    return count


def is_online(uid):
    return (cache.get(_key(uid)) or 0) > 0


def online_ids(ids):
    """Subset of `ids` that are currently online (friends-only callers)."""
    return {uid for uid in ids if is_online(uid)}
