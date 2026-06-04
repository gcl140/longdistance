import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from friends.models import Contact, FriendRequest

from .models import (
    PartyInvite,
    PartyMessage,
    VideoSession,
    WatchParty,
    WatchPartyMember,
)
from .services import send_party_invite

User = get_user_model()


def _membership(party, user):
    return WatchPartyMember.objects.filter(party=party, user=user).first()


def _is_member(party, user):
    """Host counts as a member implicitly."""
    return party.host_id == user.id or _membership(party, user) is not None


def _backfill_session_art(request, parties):
    """For older sessions missing a poster, match the video URL to a library
    movie and copy its poster/subtitle so the card shows real art."""
    from catalog.models import Movie

    needing = [p for p in parties if getattr(p, "session", None)
               and p.session.video_url and not p.session.poster_url]
    if not needing:
        return
    movies = list(Movie.objects.all())
    for p in needing:
        s = p.session
        for m in movies:
            su = m.video_file.url if m.video_file else m.video_url
            if su and (s.video_url == su or s.video_url.endswith(su)):
                if m.poster_src:
                    s.poster_url = m.poster_src if m.poster_src.startswith("http") else request.build_absolute_uri(m.poster_src)
                if not s.subtitle_url and m.subtitle_src:
                    s.subtitle_url = m.subtitle_src if m.subtitle_src.startswith("http") else request.build_absolute_uri(m.subtitle_src)
                if s.poster_url or s.subtitle_url:
                    s.save(update_fields=["poster_url", "subtitle_url"])
                break


@login_required
def my_parties(request):
    # Opportunistic housekeeping (at most once/hour, process-wide) so abandoned
    # parties get cleaned up even without a cron job. No-ops if a cron runs it.
    from django.core.cache import cache
    if cache.add("parties_pruned_recently", True, 3600):
        try:
            from .services import prune_parties
            prune_parties()
        except Exception:
            pass

    hosting = list(WatchParty.objects.filter(host=request.user, ended_at__isnull=True).select_related("session"))
    joined = list(
        WatchParty.objects.filter(members__user=request.user, ended_at__isnull=True)
        .exclude(host=request.user)
        .select_related("session")
        .distinct()
    )
    _backfill_session_art(request, hosting + joined)
    invites = PartyInvite.objects.filter(
        recipient=request.user, status="pending"
    ).select_related("party", "sender")
    return render(
        request,
        "parties/my_parties.html",
        {"hosting": hosting, "joined": joined, "invites": invites},
    )


@login_required
def create_party(request):
    from catalog.models import Movie

    if request.method == "POST":
        movie = Movie.objects.filter(id=request.POST.get("movie_id")).first()
        if not movie or not movie.is_playable or movie.is_processing:
            messages.error(request, "Pick a movie from the library to watch.")
            return redirect("parties:create")

        name = (request.POST.get("name") or "").strip() or f"{movie.title} night"
        is_private = request.POST.get("is_private") == "on"

        scheduled_for = None
        raw_sched = (request.POST.get("scheduled_for") or "").strip()
        if raw_sched:
            from datetime import datetime
            from django.utils import timezone
            try:
                dt = datetime.fromisoformat(raw_sched)
                scheduled_for = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except ValueError:
                scheduled_for = None

        party = WatchParty.objects.create(
            name=name, host=request.user, is_private=is_private,
            scheduled_for=scheduled_for,
        )
        WatchPartyMember.objects.create(
            party=party, user=request.user, is_moderator=True
        )
        VideoSession.objects.create(
            party=party,
            video_url=request.build_absolute_uri(movie.stream_url),
            subtitle_url=request.build_absolute_uri(movie.subtitle_src) if movie.subtitle_src else "",
            poster_url=request.build_absolute_uri(movie.poster_src) if movie.poster_src else "",
            title=str(movie),
        )

        # Optional: invite selected friends (restricted to the user's contacts).
        friend_ids = request.POST.getlist("invite_friends")
        if friend_ids:
            invitees = User.objects.filter(
                id__in=friend_ids,
                friend_of__user=request.user,  # they are a contact of the host
            ).distinct()
            for friend in invitees:
                send_party_invite(request, party, friend)
            if invitees:
                messages.info(request, f"Invited {len(invitees)} friend(s).")

        messages.success(
            request, f"Party “{party.name}” created. Share code {party.access_code}."
        )
        return redirect("parties:room", code=party.access_code)

    # Has at least one playable (not-processing) movie = NOT (both sources empty).
    has_movies = (
        Movie.objects.exclude(transcode_status="processing")
        .exclude(video_file="", video_url="")
        .exists()
    )
    contacts = (
        Contact.objects.filter(user=request.user, is_blocked=False)
        .select_related("friend")
    )
    return render(
        request,
        "parties/create.html",
        {"has_movies": has_movies, "contacts": contacts},
    )


@login_required
def join_party(request):
    if request.method == "POST":
        code = (request.POST.get("access_code") or "").strip()
        party = WatchParty.objects.filter(
            access_code=code, ended_at__isnull=True
        ).first()
        if not party:
            messages.error(request, "No active party found with that code.")
            return redirect("parties:join")
        WatchPartyMember.objects.get_or_create(party=party, user=request.user)
        messages.success(request, f"Joined “{party.name}”.")
        return redirect("parties:room", code=party.access_code)
    return render(request, "parties/join.html")


@login_required
def room(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    if party.ended_at is not None:
        messages.info(request, "This party has ended.")
        return redirect("parties:my_parties")

    if not _is_member(party, request.user):
        if party.is_private:
            messages.error(
                request, "This party is private — you need an invite or the code."
            )
            return redirect("parties:my_parties")
        WatchPartyMember.objects.get_or_create(party=party, user=request.user)

    session, _ = VideoSession.objects.get_or_create(party=party)
    member = _membership(party, request.user)
    if member:
        member.last_seen = now()
        member.save(update_fields=["last_seen"])

    is_host = party.host_id == request.user.id
    can_control = is_host or (member.is_moderator if member else False)

    invitable = (
        Contact.objects.filter(user=request.user, is_blocked=False)
        .exclude(friend__in=party.members.values_list("user", flat=True))
        .select_related("friend")
    )

    # For the People tab's "add friend" hover icon: who's already a friend and
    # who has a request pending from me, so we show the right control per member.
    my_friend_ids = set(
        Contact.objects.filter(user=request.user).values_list("friend_id", flat=True)
    )
    pending_ids = set(
        FriendRequest.objects.filter(
            from_user=request.user, status=FriendRequest.PENDING
        ).values_list("to_user_id", flat=True)
    )

    return render(
        request,
        "parties/room.html",
        {
            "party": party,
            "session": session,
            "is_host": is_host,
            "can_control": can_control,
            "members": party.members.select_related("user"),
            "invitable": invitable,
            "my_friend_ids": my_friend_ids,
            "pending_ids": pending_ids,
        },
    )


# ---- JSON endpoints (HTTP polling stand-in until Channels lands) ----

@login_required
def session_state(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    s = get_object_or_404(VideoSession, party=party)
    return JsonResponse(
        {
            "is_playing": s.is_playing,
            "current_position": s.current_position,
            "playback_rate": s.playback_rate,
            "video_url": s.video_url,
            "title": s.title,
            "updated_at": s.updated_at.timestamp(),
            "ended": party.ended_at is not None,
        }
    )


@login_required
@require_POST
def session_update(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    member = _membership(party, request.user)
    can_control = party.host_id == request.user.id or (member and member.is_moderator)
    if not can_control:
        return JsonResponse({"error": "Only the host can control playback."}, status=403)

    s = get_object_or_404(VideoSession, party=party)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    if "is_playing" in data:
        s.is_playing = bool(data["is_playing"])
    if "current_position" in data:
        s.current_position = float(data["current_position"])
    if "playback_rate" in data:
        s.playback_rate = float(data["playback_rate"])
    if "video_url" in data:
        s.video_url = data["video_url"] or ""
    if "title" in data:
        s.title = data["title"] or ""
    s.save()
    return JsonResponse({"ok": True, "updated_at": s.updated_at.timestamp()})


@login_required
def messages_json(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    if not _is_member(party, request.user):
        return JsonResponse({"error": "Not a member."}, status=403)
    after = request.GET.get("after")
    qs = party.messages.select_related("sender")
    if after:
        qs = qs.filter(id__gt=after)
    data = [
        {
            "id": m.id,
            "sender": m.sender.get_full_name().strip() or m.sender.nickname,
            "sender_id": m.sender_id,
            "is_me": m.sender_id == request.user.id,
            "message": m.message,
            "at": m.created_at.strftime("%H:%M"),
        }
        for m in qs[:200]
    ]
    return JsonResponse({"messages": data})


@login_required
@require_POST
def send_message(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    if not _is_member(party, request.user):
        return JsonResponse({"error": "Not a member."}, status=403)
    text = (request.POST.get("message") or "").strip()
    if not text:
        return JsonResponse({"error": "Empty message."}, status=400)
    m = PartyMessage.objects.create(
        party=party, sender=request.user, message=text[:2000]
    )
    return JsonResponse({"ok": True, "id": m.id})


@login_required
@require_POST
def leave_party(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    WatchPartyMember.objects.filter(party=party, user=request.user).delete()
    messages.info(request, f"You left “{party.name}”.")
    return redirect("parties:my_parties")


@login_required
@require_POST
def end_party(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    if party.host_id != request.user.id:
        messages.error(request, "Only the host can end the party.")
        return redirect("parties:room", code=code)
    party.ended_at = now()
    party.save(update_fields=["ended_at"])
    messages.success(request, f"“{party.name}” has ended.")
    return redirect("parties:my_parties")


@login_required
@require_POST
def invite_to_party(request, code):
    party = get_object_or_404(WatchParty, access_code=code)
    if not _is_member(party, request.user):
        messages.error(request, "You're not in this party.")
        return redirect("parties:my_parties")
    recipient = User.objects.filter(id=request.POST.get("recipient")).first()
    if not recipient:
        messages.error(request, "User not found.")
        return redirect("parties:room", code=code)
    send_party_invite(request, party, recipient)
    messages.success(
        request, f"Invited {recipient.get_full_name().strip() or recipient.email}."
    )
    return redirect("parties:room", code=code)
