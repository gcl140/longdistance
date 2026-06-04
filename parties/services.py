"""Party invitations: in-app notification always, email only when offline.

The rule (per product spec): if the friend is **online**, they get a real-time
in-app ding only — no email. If they're **offline**, we still record the
notification (so they see it when they return) AND send them an email with the
movie, time, access code, and a join link.
"""

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from notifications import presence
from notifications.models import Notification
from notifications.services import push_notification

from .models import PartyInvite


def prune_parties(stale_hours=None, keep_days=None):
    """Housekeeping so parties don't pile up:

    1. Auto-end *active* parties with no activity for `stale_hours` (abandoned
       rooms nobody closed). Future-scheduled parties are never touched.
    2. Delete *ended* parties older than `keep_days` — cascades their
       VideoSession / messages / members / invites.

    Returns (ended_count, deleted_count). Safe to call repeatedly.
    """
    from datetime import timedelta

    from django.db.models import Max

    from .models import WatchParty

    stale_hours = stale_hours if stale_hours is not None else getattr(settings, "PARTY_STALE_HOURS", 8)
    keep_days = keep_days if keep_days is not None else getattr(settings, "PARTY_KEEP_DAYS", 7)
    now = timezone.now()

    # 1) End abandoned active rooms.
    stale_before = now - timedelta(hours=stale_hours)
    ended = 0
    active = (
        WatchParty.objects.filter(ended_at__isnull=True)
        .select_related("session")
        .annotate(last_msg=Max("messages__created_at"), last_seen=Max("members__last_seen"))
    )
    for p in active:
        if p.scheduled_for and p.scheduled_for > now:
            continue  # scheduled for the future — leave it alone
        try:
            session_updated = p.session.updated_at
        except ObjectDoesNotExist:
            session_updated = None
        ref = p.scheduled_for or p.created_at
        last_activity = max(c for c in (ref, p.last_msg, p.last_seen, session_updated) if c)
        if last_activity < stale_before:
            p.ended_at = now
            p.save(update_fields=["ended_at"])
            ended += 1

    # 2) Delete long-ended rooms (cascade removes session/messages/members/invites).
    old = WatchParty.objects.filter(ended_at__lt=now - timedelta(days=keep_days))
    deleted = old.count()
    old.delete()
    return ended, deleted


def _display(user):
    return user.get_full_name().strip() or user.email


def _movie_title(party):
    try:
        if party.session and party.session.title:
            return party.session.title
    except ObjectDoesNotExist:  # no VideoSession yet
        pass
    return party.name


def _when_phrase(party):
    if party.scheduled_for:
        return "on " + timezone.localtime(party.scheduled_for).strftime("%b %-d at %-I:%M %p")
    return "right now"


def send_party_invite(request, party, recipient):
    """Invite `recipient` to `party`; notify in-app, email if they're offline.

    Returns the (invite, created) tuple. Skips silently if the recipient is
    already the host or already invited (get_or_create handles the latter).
    """
    sender = request.user
    if recipient.id == party.host_id and recipient.id == sender.id:
        return None, False

    invite, created = PartyInvite.objects.get_or_create(
        party=party, recipient=recipient, defaults={"sender": sender}
    )

    movie = _movie_title(party)
    join_url = request.build_absolute_uri(
        reverse("parties:room", args=[party.access_code])
    )

    push_notification(
        recipient=recipient,
        actor=sender,
        kind=Notification.PARTY_INVITE,
        title=f"{_display(sender)} invited you to watch {movie}",
        body=f"Watch party {_when_phrase(party)} · code {party.access_code}",
        url=join_url,
        data={"invite_id": invite.id, "code": party.access_code},
    )

    # Online → in-app ding is enough. Offline → also email them.
    if not presence.is_online(recipient.id):
        _email_invite(sender, recipient, party, movie, join_url)

    return invite, created


def _email_invite(sender, recipient, party, movie, join_url):
    if not settings.EMAIL_HOST_USER:
        return  # SMTP not configured (e.g. local dev without creds)
    subject = f"{_display(sender)} wants to watch {movie} with you on Lisa"
    when = _when_phrase(party)
    body = (
        f"{_display(sender)} invited you to a Lisa watch party {when}.\n\n"
        f"Movie: {movie}\n"
        f"Join with code: {party.access_code}\n"
        f"Or open this link: {join_url}\n\n"
        f"See you there!\n— Lisa"
    )
    html = (
        f"<p>{_display(sender)} invited you to a Lisa watch party <b>{when}</b>.</p>"
        f"<p><b>Movie:</b> {movie}<br>"
        f"<b>Code:</b> {party.access_code}</p>"
        f'<p><a href="{join_url}" '
        f'style="background:#E50914;color:#fff;padding:10px 18px;border-radius:6px;'
        f'text-decoration:none;font-weight:600;">Join the watch party</a></p>'
        f'<p style="color:#888;font-size:12px;">Or paste this link: {join_url}</p>'
    )
    try:
        send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, [recipient.email],
            html_message=html, fail_silently=True,
        )
    except Exception:
        pass
