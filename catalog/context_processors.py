"""Template-wide context — injects request-quota state into every page so the
nav chip can render without an extra round-trip."""

from .quota import format_mb, user_quota


def request_quota(request):
    if not hasattr(request, "user"):
        return {}
    q = user_quota(request.user)
    return {
        "request_quota": {
            **q,
            "used_label": format_mb(q["used_mb"]),
            "limit_label": format_mb(q["limit_mb"]),
            "remaining_label": format_mb(q["remaining_mb"]),
        }
    }
