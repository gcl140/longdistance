import calendar as _cal
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from parties.models import WatchParty

User = get_user_model()
FEED_SALT = "lisa-calendar-feed"
EVENT_HOURS = 2  # assumed movie-night length for calendar blocks


def _user_scheduled_parties(user):
    """Scheduled, not-yet-ended parties the user hosts, joined, or was invited to."""
    return (
        WatchParty.objects.filter(scheduled_for__isnull=False, ended_at__isnull=True)
        .filter(
            Q(host=user)
            | Q(members__user=user)
            | Q(invites__recipient=user, invites__status="pending")
        )
        .distinct()
        .order_by("scheduled_for")
    )


@login_required
def calendar_view(request):
    today = timezone.localtime()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except ValueError:
        year, month = today.year, today.month
    if not 1 <= month <= 12:
        year, month = today.year, today.month

    parties = _user_scheduled_parties(request.user)

    # Bucket parties by local date for the grid.
    by_day = {}
    upcoming = []
    now = timezone.now()
    for p in parties:
        local = timezone.localtime(p.scheduled_for)
        if local.year == year and local.month == month:
            by_day.setdefault(local.day, []).append((p, local))
        if p.scheduled_for >= now:
            upcoming.append((p, local))

    cal = _cal.Calendar(firstweekday=6)  # Sunday-first
    weeks = cal.monthdayscalendar(year, month)  # lists of day numbers (0 = padding)

    prev_month = (datetime(year, month, 1) - timedelta(days=1))
    next_month = (datetime(year, month, 28) + timedelta(days=7)).replace(day=1)

    token = signing.dumps(request.user.pk, salt=FEED_SALT)
    feed_url = request.build_absolute_uri(
        reverse("schedule:feed", args=[token])
    )

    return render(request, "schedule/calendar.html", {
        "year": year, "month": month,
        "month_name": _cal.month_name[month],
        "weeks": weeks,
        "by_day": by_day,
        "today": today,
        "upcoming": upcoming[:10],
        "prev": {"year": prev_month.year, "month": prev_month.month},
        "next": {"year": next_month.year, "month": next_month.month},
        "weekday_labels": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "feed_url": feed_url,
    })


# ---------- iCalendar (.ics) ----------

def _ics_escape(text):
    return (str(text or "")
            .replace("\\", "\\\\").replace(",", "\\,")
            .replace(";", "\\;").replace("\n", "\\n"))


def _fmt(dt):
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent(party, request):
    start = party.scheduled_for
    end = start + timedelta(hours=EVENT_HOURS)
    url = request.build_absolute_uri(
        reverse("parties:room", args=[party.access_code])
    )
    summary = party.name
    try:
        if party.session and party.session.title:
            summary = f"{party.name}: {party.session.title}"
    except WatchParty.session.RelatedObjectDoesNotExist:
        pass
    return "\r\n".join([
        "BEGIN:VEVENT",
        f"UID:lisa-{party.access_code}@lisa",
        f"DTSTAMP:{_fmt(timezone.now())}",
        f"DTSTART:{_fmt(start)}",
        f"DTEND:{_fmt(end)}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{_ics_escape('Watch party on Lisa. Join: ' + url)}",
        f"URL:{url}",
        "END:VEVENT",
    ])


def _calendar_doc(vevents):
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lisa//Watch Party//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        *vevents,
        "END:VCALENDAR",
        "",
    ])


@login_required
def ics_event(request, code):
    """Single 'Add to Calendar' download for one scheduled party."""
    party = WatchParty.objects.filter(access_code=code, scheduled_for__isnull=False).first()
    if not party:
        raise Http404("Not a scheduled party.")
    doc = _calendar_doc([_vevent(party, request)])
    resp = HttpResponse(doc, content_type="text/calendar")
    resp["Content-Disposition"] = f'attachment; filename="lisa-{code}.ics"'
    return resp


def ics_feed(request, token):
    """Subscribable feed of all a user's upcoming parties (no login — token-auth)."""
    try:
        uid = signing.loads(token, salt=FEED_SALT, max_age=60 * 60 * 24 * 365)
    except signing.BadSignature:
        raise Http404("Invalid calendar feed.")
    user = User.objects.filter(pk=uid).first()
    if not user:
        raise Http404("Unknown user.")
    parties = _user_scheduled_parties(user)
    doc = _calendar_doc([_vevent(p, request) for p in parties])
    return HttpResponse(doc, content_type="text/calendar")
