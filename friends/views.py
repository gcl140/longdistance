from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from notifications.models import Notification
from notifications.services import push_notification
from parties.models import PartyInvite, WatchPartyMember

from .models import Contact, FriendRequest

User = get_user_model()


def _display(user):
    return user.get_full_name().strip() or user.email


def _are_friends(a, b):
    return Contact.objects.filter(user=a, friend=b).exists()


def _link_friends(a, b):
    """Create the two symmetric Contact rows for a mutual friendship."""
    Contact.objects.get_or_create(user=a, friend=b)
    Contact.objects.get_or_create(user=b, friend=a)


def _safe_next(request, fallback):
    """A POSTed `next` URL, but only if it's a local path."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and nxt.startswith("/"):
        return nxt
    return fallback


@login_required
def friends_list(request):
    contacts = list(
        Contact.objects.filter(user=request.user).select_related("friend")
    )
    favorites = [c for c in contacts if c.is_favorite]
    others = [c for c in contacts if not c.is_favorite]
    incoming = (
        FriendRequest.objects.filter(to_user=request.user, status=FriendRequest.PENDING)
        .select_related("from_user")
    )
    return render(
        request,
        "friends/friends.html",
        {"contacts": contacts, "favorites": favorites, "others": others, "incoming": incoming},
    )


@login_required
def search(request):
    """Autocomplete for the add-friend box.

    Matches email + name, EMAIL-FIRST: exact email, then email prefix, then
    name contains. Excludes yourself and people you're already friends with.
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    friend_ids = list(
        Contact.objects.filter(user=request.user).values_list("friend_id", flat=True)
    )
    qs = (
        User.objects.exclude(id=request.user.id)
        .exclude(id__in=friend_ids)
        .filter(
            Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )[:25]
    )

    ql = q.lower()
    pending_out = set(
        FriendRequest.objects.filter(
            from_user=request.user, status=FriendRequest.PENDING
        ).values_list("to_user_id", flat=True)
    )

    def rank(u):
        email = (u.email or "").lower()
        if email == ql:
            return 0
        if email.startswith(ql):
            return 1
        if ql in email:
            return 2
        return 3

    ranked = sorted(qs, key=rank)[:8]
    results = [
        {
            "id": u.id,
            "name": _display(u),
            "email": u.email,
            "initial": (_display(u)[:1] or "?").upper(),
            "pending": u.id in pending_out,
        }
        for u in ranked
    ]
    return JsonResponse({"results": results})


@login_required
@require_POST
def send_request(request):
    """Send a friend request by user id (autocomplete) or raw email.

    If the target already sent *you* a pending request, this accepts it instead
    of creating a mirror request. Redirects back to `next` (e.g. a party room)
    when provided, else the friends list.
    """
    fallback = reverse("friends:list")
    target = None
    uid = request.POST.get("user_id")
    if uid:
        target = User.objects.filter(id=uid).first()
    else:
        email = (request.POST.get("email") or "").strip().lower()
        if email:
            target = User.objects.filter(email__iexact=email).first()

    if not target:
        messages.error(request, "No Lisa user found.")
        return redirect(_safe_next(request, fallback))
    if target.id == request.user.id:
        messages.error(request, "You can't add yourself.")
        return redirect(_safe_next(request, fallback))
    if _are_friends(request.user, target):
        messages.info(request, f"You're already friends with {_display(target)}.")
        return redirect(_safe_next(request, fallback))

    # They already asked you — accept rather than create a mirror request.
    incoming = FriendRequest.objects.filter(
        from_user=target, to_user=request.user, status=FriendRequest.PENDING
    ).first()
    if incoming:
        _accept_request(incoming, request.user)
        messages.success(request, f"You're now friends with {_display(target)}.")
        return redirect(_safe_next(request, fallback))

    fr, created = FriendRequest.objects.get_or_create(
        from_user=request.user, to_user=target
    )
    if not created and fr.status == FriendRequest.PENDING:
        messages.info(request, f"Request to {_display(target)} already sent.")
        return redirect(_safe_next(request, fallback))
    if not created:
        # Re-open a previously declined request.
        fr.status = FriendRequest.PENDING
        fr.responded_at = None
        fr.save(update_fields=["status", "responded_at"])

    push_notification(
        recipient=target,
        actor=request.user,
        kind=Notification.FRIEND_REQUEST,
        title=f"{_display(request.user)} sent you a friend request",
        url=reverse("friends:list"),
        data={"friend_request_id": fr.id},
    )
    messages.success(request, f"Friend request sent to {_display(target)}.")
    return redirect(_safe_next(request, fallback))


def _accept_request(fr, recipient):
    """Mark a request accepted, link the friendship, notify the sender."""
    fr.status = FriendRequest.ACCEPTED
    fr.responded_at = now()
    fr.save(update_fields=["status", "responded_at"])
    _link_friends(fr.from_user, fr.to_user)
    # Clear the original request notification from the recipient's bell.
    Notification.objects.filter(
        recipient=recipient,
        kind=Notification.FRIEND_REQUEST,
        data__friend_request_id=fr.id,
    ).update(is_read=True)
    push_notification(
        recipient=fr.from_user,
        actor=recipient,
        kind=Notification.FRIEND_ACCEPTED,
        title=f"{_display(recipient)} accepted your friend request",
        url=reverse("friends:list"),
    )


@login_required
@require_POST
def respond_request(request, request_id, action):
    """Approve or reject an incoming friend request. Returns JSON for the modal."""
    fr = get_object_or_404(FriendRequest, id=request_id, to_user=request.user)
    if fr.status != FriendRequest.PENDING:
        return JsonResponse({"ok": True, "status": fr.status, "stale": True})

    if action == "accept":
        _accept_request(fr, request.user)
        return JsonResponse({
            "ok": True, "status": "accepted",
            "message": f"You're now friends with {_display(fr.from_user)}.",
        })

    fr.status = FriendRequest.DECLINED
    fr.responded_at = now()
    fr.save(update_fields=["status", "responded_at"])
    Notification.objects.filter(
        recipient=request.user,
        kind=Notification.FRIEND_REQUEST,
        data__friend_request_id=fr.id,
    ).update(is_read=True)
    return JsonResponse({"ok": True, "status": "declined", "message": "Request declined."})


@login_required
@require_POST
def remove_friend(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id, user=request.user)
    friend = contact.friend
    contact.delete()
    Contact.objects.filter(user=friend, friend=request.user).delete()
    messages.info(request, "Friend removed.")
    return redirect("friends:list")


@login_required
@require_POST
def toggle_favorite(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id, user=request.user)
    contact.is_favorite = not contact.is_favorite
    contact.save(update_fields=["is_favorite"])
    return redirect("friends:list")


@login_required
@require_POST
def respond_invite(request, invite_id, action):
    invite = get_object_or_404(PartyInvite, id=invite_id, recipient=request.user)
    if action == "accept":
        invite.status = "accepted"
        invite.responded_at = now()
        invite.save(update_fields=["status", "responded_at"])
        WatchPartyMember.objects.get_or_create(party=invite.party, user=request.user)
        messages.success(request, f"Joined “{invite.party.name}”.")
        return redirect("parties:room", code=invite.party.access_code)
    else:
        invite.status = "declined"
        invite.responded_at = now()
        invite.save(update_fields=["status", "responded_at"])
        messages.info(request, "Invite declined.")
        return redirect("parties:my_parties")
