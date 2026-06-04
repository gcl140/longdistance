"""Per-user movie-request quota.

Normal users get 5GB of total requests (sum of estimated file sizes). Once they
hit the cap, new requests are rejected. Admins (is_staff) are exempt.

The "5GB" is the server's storage budget — it's NOT about what's been watched,
just what users have asked us to acquire."""

from django.conf import settings
from django.db.models import Sum

# Tunables — overridable via Django settings.
DEFAULT_QUOTA_MB = 5 * 1024  # 5GB
DEFAULT_MB_PER_MIN = 20      # ~1080p WEB-DL: a 90-min film ≈ 1.8GB
DEFAULT_FALLBACK_MB = 1500   # missing runtime → assume 1.5GB

# Requests in these states still consume quota. Rejected ones free the slot back up.
COUNTED_STATUSES = ("pending", "approved", "fulfilled")


def _conf(name, default):
    return getattr(settings, name, default)


def estimate_size_mb(tmdb_data):
    """File-size estimate from a tmdb_data dict (uses runtime in minutes)."""
    runtime = (tmdb_data or {}).get("runtime") or 0
    try:
        runtime = int(runtime)
    except (TypeError, ValueError):
        runtime = 0
    if runtime > 0:
        return runtime * _conf("REQUEST_SIZE_MB_PER_MIN", DEFAULT_MB_PER_MIN)
    return _conf("REQUEST_SIZE_FALLBACK_MB", DEFAULT_FALLBACK_MB)


def user_quota(user):
    """Snapshot of a user's request quota.

    Returns {used_mb, limit_mb, remaining_mb, percent, blocked, unlimited}.
    Admins are flagged `unlimited=True` and never blocked."""
    limit = _conf("REQUEST_QUOTA_MB", DEFAULT_QUOTA_MB)
    if not user.is_authenticated:
        return {
            "used_mb": 0, "limit_mb": limit, "remaining_mb": limit,
            "percent": 0, "blocked": False, "unlimited": False,
        }
    if user.is_staff:
        return {
            "used_mb": 0, "limit_mb": limit, "remaining_mb": limit,
            "percent": 0, "blocked": False, "unlimited": True,
        }

    from .models import MovieRequest

    used = MovieRequest.objects.filter(
        requester=user, status__in=COUNTED_STATUSES
    ).aggregate(t=Sum("estimated_size_mb"))["t"] or 0
    remaining = max(0, limit - used)
    percent = min(100, int((used / limit) * 100)) if limit else 0
    return {
        "used_mb": used,
        "limit_mb": limit,
        "remaining_mb": remaining,
        "percent": percent,
        # The rule: block when existing total is already at/over the cap. A
        # single request that pushes you slightly over still goes through.
        "blocked": used >= limit,
        "unlimited": False,
    }


def format_mb(mb):
    """Human-friendly size: 1500 → '1.5 GB', 600 → '600 MB'."""
    if mb is None:
        return ""
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{int(mb)} MB"
