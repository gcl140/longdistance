from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import presence
from .models import Notification

PAGE_SIZE = 15


@login_required
def friends_presence(request):
    """Which of the current user's friends are online right now.

    Friends-only by construction: we only ever check the requester's contacts.
    """
    from friends.models import Contact

    friend_ids = list(
        Contact.objects.filter(user=request.user).values_list("friend_id", flat=True)
    )
    return JsonResponse({"online": sorted(presence.online_ids(friend_ids))})


@login_required
def feed(request):
    """Paginated JSON of the user's notifications (for the bell dropdown)."""
    qs = Notification.objects.filter(recipient=request.user)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page") or 1)
    return JsonResponse({
        "results": [n.as_dict() for n in page.object_list],
        "unread": qs.filter(is_read=False).count(),
        "has_next": page.has_next(),
        "page": page.number,
    })


@login_required
def unread_count(request):
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({"unread": count})


@login_required
@require_POST
def mark_read(request, note_id):
    Notification.objects.filter(id=note_id, recipient=request.user).update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
def notification_list(request):
    """Server-rendered paginated history page (the bell's 'See all')."""
    qs = Notification.objects.filter(recipient=request.user)
    page = Paginator(qs, 25).get_page(request.GET.get("page") or 1)
    # Opening the full list marks everything read.
    qs.filter(is_read=False).update(is_read=True)
    return render(request, "notifications/list.html", {"page": page})
