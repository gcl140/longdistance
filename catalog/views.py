import json
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import MovieForm
from .models import Movie, MovieRequest
from .quota import estimate_size_mb, format_mb, user_quota

TMDB_BASE = "https://api.themoviedb.org/3"
staff_required = user_passes_test(lambda u: u.is_staff)


def _tmdb(path, params):
    """Call a TMDb v3 endpoint and return parsed JSON (or None on failure)."""
    key = settings.TMDB_API_KEY
    if not key:
        return None
    params = {**params, "api_key": key}
    url = f"{TMDB_BASE}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _poster(path):
    return f"{settings.TMDB_IMAGE_BASE}{path}" if path else ""


def _backdrop(path):
    """Wide HD image for the hero/billboard (w1280 vs the w500 used for posters)."""
    return f"{settings.TMDB_BACKDROP_BASE}{path}" if path else ""


def _download_poster(movie, url):
    """Stash a remote poster image locally on movie.poster.

    Skips when a manual poster file is already present, or the download fails —
    poster_url stays as the upstream reference either way."""
    if not url or movie.poster:
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lisa/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            ct = (resp.headers.get("Content-Type") or "").lower()
    except Exception:
        return False
    from django.core.files.base import ContentFile
    from django.utils.text import slugify

    if "png" in ct:
        ext = "png"
    elif "webp" in ct:
        ext = "webp"
    else:
        path = url.split("?", 1)[0].lower()
        ext = "png" if path.endswith(".png") else "webp" if path.endswith(".webp") else "jpg"
    slug = slugify(movie.title) or "movie"
    folder = f"{slug}-{movie.tmdb_id}" if movie.tmdb_id else slug
    movie.poster.save(f"{folder}/poster.{ext}", ContentFile(data), save=False)
    return True


def _normalize(item):
    title = item.get("title") or item.get("name") or "Untitled"
    date = item.get("release_date") or item.get("first_air_date") or ""
    return {
        "id": item.get("id"),
        "title": title,
        "year": date[:4] if date else "",
        "poster": _poster(item.get("poster_path")),
        "backdrop": _backdrop(item.get("backdrop_path")),
        "overview": item.get("overview", ""),
        "media_type": item.get("media_type", "movie"),
        "rating": item.get("vote_average"),
        "vote_count": item.get("vote_count"),
    }


def _extract_certification(detail, media_type):
    """Age rating: US theatrical cert for movies, US content rating for TV."""
    try:
        if media_type == "tv":
            for r in (detail.get("content_ratings") or {}).get("results", []):
                if r.get("iso_3166_1") == "US" and r.get("rating"):
                    return r["rating"]
        else:
            for r in (detail.get("release_dates") or {}).get("results", []):
                if r.get("iso_3166_1") == "US":
                    for rd in r.get("release_dates", []):
                        if rd.get("certification"):
                            return rd["certification"]
    except Exception:
        pass
    return ""


def fetch_tmdb_details(tmdb_id, media_type="movie"):
    """Pull a TMDb detail record + trailer + cast/crew + age cert. None on failure."""
    if not tmdb_id:
        return None
    is_tv = media_type == "tv"
    path = f"/{'tv' if is_tv else 'movie'}/{tmdb_id}"
    append = "videos,credits,content_ratings" if is_tv else "videos,credits,release_dates"
    detail = _tmdb(path, {"append_to_response": append})
    if not detail:
        return None

    videos = (detail.get("videos") or {}).get("results") or []
    trailer = next(
        (v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"),
        None,
    ) or next((v for v in videos if v.get("site") == "YouTube"), None)

    credits = detail.get("credits") or {}
    cast = [
        {
            "name": c.get("name"),
            "character": c.get("character") or "",
            "profile": _poster(c.get("profile_path")) if c.get("profile_path") else "",
        }
        # TMDb returns cast pre-sorted by `order` (lead actors first); top 5 is plenty.
        for c in (credits.get("cast") or [])[:5] if c.get("name")
    ]
    directors = [
        c.get("name") for c in (credits.get("crew") or [])
        if c.get("job") == "Director" and c.get("name")
    ]
    # TV uses "created_by" instead of a director credit.
    if is_tv and not directors:
        directors = [c.get("name") for c in (detail.get("created_by") or []) if c.get("name")]

    date = detail.get("release_date") or detail.get("first_air_date") or ""
    return {
        "tmdb_id": detail.get("id"),
        "title": detail.get("title") or detail.get("name") or "",
        "year": date[:4] if date else "",
        "overview": detail.get("overview") or "",
        "tagline": detail.get("tagline") or "",
        "rating": detail.get("vote_average"),
        "vote_count": detail.get("vote_count"),
        "runtime": detail.get("runtime") or (detail.get("episode_run_time") or [None])[0],
        "genres": [g.get("name") for g in (detail.get("genres") or []) if g.get("name")],
        "cast": cast,
        "directors": directors,
        "certification": _extract_certification(detail, media_type),
        "poster_path": detail.get("poster_path") or "",
        "backdrop_path": detail.get("backdrop_path") or "",
        "poster_url": _poster(detail.get("poster_path")),
        "backdrop_url": _backdrop(detail.get("backdrop_path")),
        "trailer_key": trailer.get("key") if trailer else "",
        "media_type": "tv" if is_tv else "movie",
    }


def _annotate_with_library(results, user):
    """Tag each TMDb result with in_library / requested state so the UI can branch.

    Looks up Movie + MovieRequest by tmdb_id in a single round-trip each."""
    ids = [r["id"] for r in results if r.get("id")]
    if not ids:
        return results
    in_lib = {
        m.tmdb_id: m
        for m in Movie.objects.filter(tmdb_id__in=ids).only(
            "id", "tmdb_id", "video_file", "video_url", "transcode_status"
        )
    }
    reqs = {
        r.tmdb_id: r
        for r in MovieRequest.objects.filter(
            tmdb_id__in=ids, status__in=("pending", "approved")
        ).prefetch_related("voters")
    }
    uid = user.id if user.is_authenticated else None
    for r in results:
        m = in_lib.get(r["id"])
        if m:
            r["in_library"] = True
            r["library_id"] = m.id
            r["playable"] = m.is_playable and not m.is_processing
        else:
            r["in_library"] = False
        req = reqs.get(r["id"])
        if req:
            r["request_id"] = req.id
            r["request_status"] = req.status
            r["vote_count"] = req.vote_count
            r["voted"] = bool(uid and req.voters.filter(id=uid).exists())
    return results


@login_required
def request_state(request):
    """Live status for a batch of TMDb ids — drives the search dropdown's
    "Requested → spinner → green tick" indicator without re-searching TMDb."""
    raw = (request.GET.get("ids") or "").split(",")
    ids = [int(x) for x in raw if x.strip().isdigit()][:50]
    states = {}
    if ids:
        movies = {m.tmdb_id: m for m in Movie.objects.filter(tmdb_id__in=ids)}
        reqs = {r.tmdb_id: r for r in MovieRequest.objects.filter(tmdb_id__in=ids)}
        for i in ids:
            m, rq = movies.get(i), reqs.get(i)
            states[str(i)] = {
                "in_library": bool(m),
                "library_id": m.id if m else None,
                "playable": (m.is_playable and not m.is_processing) if m else False,
                "request_status": rq.status if rq else None,
            }
    return JsonResponse({"states": states})


@login_required
def search(request):
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": [], "error": "Type something to search."})
    if not settings.TMDB_API_KEY:
        return JsonResponse({"results": [], "error": "TMDb not configured — set TMDB_API_KEY in .env."})
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    data = _tmdb("/search/multi", {"query": q, "include_adult": "false", "page": page})
    if data is None:
        return JsonResponse({"results": [], "error": "Could not reach TMDb."})
    results = [
        _normalize(i) for i in data.get("results", [])
        if i.get("media_type") in ("movie", "tv")
    ]
    _annotate_with_library(results, request.user)
    return JsonResponse({
        "results": results,
        "page": data.get("page", 1),
        "total_pages": data.get("total_pages", 1),
        "quota": user_quota(request.user),
    })


def trending(request):
    """Public — used to populate the landing browse rows when a key is set."""
    if not settings.TMDB_API_KEY:
        return JsonResponse({"results": []})
    data = _tmdb("/trending/all/week", {})
    if data is None:
        return JsonResponse({"results": []})
    results = [
        _normalize(i) for i in data.get("results", [])
        if i.get("media_type") in ("movie", "tv")
    ][:18]
    if request.user.is_authenticated:
        _annotate_with_library(results, request.user)
    return JsonResponse({"results": results})


# ---------- Library (uploaded / hosted movies) ----------

LIBRARY_PAGE_SIZE = 18


@login_required
def library(request):
    """The hosted movie library, filterable by TMDb genre and paginated.

    Genres live inside each movie's `tmdb_data` JSON (a list of names), which
    SQLite can't query directly — so we filter in Python. The library is small
    (self-hosted files), so this is cheap.
    """
    from .models import TMDB_MOVIE_GENRES

    all_movies = list(Movie.objects.all())

    # Genres actually present in the library, ordered by TMDb's canonical list.
    present = {g for m in all_movies for g in m.genre_list}
    order = {name: i for i, name in enumerate(TMDB_MOVIE_GENRES)}
    genres = sorted(present, key=lambda g: (order.get(g, len(order)), g))

    active_genre = (request.GET.get("genre") or "").strip()
    if active_genre and active_genre in present:
        movies = [m for m in all_movies if active_genre in m.genre_list]
    else:
        active_genre = ""
        movies = all_movies

    page = Paginator(movies, LIBRARY_PAGE_SIZE).get_page(request.GET.get("page") or 1)
    return render(request, "catalog/library.html", {
        "page": page,
        "movies": page.object_list,
        "genres": genres,
        "active_genre": active_genre,
    })


@login_required
@staff_required
def upload_movie(request):
    initial = {
        "title": request.GET.get("title", ""),
        "year": request.GET.get("year", ""),
        "description": request.GET.get("description", ""),
        "poster_url": request.GET.get("poster_url", ""),
        "tmdb_id": request.GET.get("tmdb_id") or None,
    }
    # If admin landed here from a request's "fulfill" link (?tmdb_id=…), pull the
    # TMDb snapshot now so description/title/year/poster come pre-filled even
    # when the query string didn't include them.
    if request.method == "GET" and initial["tmdb_id"]:
        try:
            tmdb_id = int(initial["tmdb_id"])
        except (TypeError, ValueError):
            tmdb_id = None
        if tmdb_id:
            details = fetch_tmdb_details(tmdb_id) or {}
            if details:
                initial["title"] = initial["title"] or details.get("title", "")
                initial["year"] = initial["year"] or details.get("year", "")
                initial["description"] = initial["description"] or details.get("overview", "")
                initial["poster_url"] = initial["poster_url"] or details.get("poster_url", "")
    if request.method == "POST":
        form = MovieForm(request.POST, request.FILES)
        if form.is_valid():
            movie = form.save(commit=False)
            movie.added_by = request.user
            # Autopopulate the TMDb snapshot when the form has a tmdb_id but no
            # existing data — keeps ratings/trailer/etc. in sync without manual entry.
            if movie.tmdb_id and not movie.tmdb_data:
                details = fetch_tmdb_details(movie.tmdb_id)
                if details:
                    movie.tmdb_data = details
                    if not movie.description:
                        movie.description = details.get("overview", "")
                    # Mirror TMDb's poster URL into the form field so the
                    # downloader below picks it up (admin can paste their own).
                    if not movie.poster_url:
                        movie.poster_url = details.get("poster_url", "")
            # Pull the poster down to local media so we don't hot-link forever.
            _download_poster(movie, movie.poster_url)
            movie.save()
            # If this fulfils a pending MovieRequest, close it out so admins see why.
            if movie.tmdb_id:
                MovieRequest.objects.filter(
                    tmdb_id=movie.tmdb_id, status__in=("pending", "approved")
                ).update(
                    status="fulfilled", fulfilled_movie=movie,
                    reviewed_at=timezone.now(),
                )

            # If they uploaded a non-MP4 file, convert it to a browser-friendly
            # MP4 in the background (the original keeps it watchable meanwhile).
            from .transcode import get_ffmpeg, kick_off, needs_transcode
            if movie.video_file and needs_transcode(movie.video_file.name) and get_ffmpeg():
                movie.transcode_status = "processing"
                movie.save(update_fields=["transcode_status"])
                kick_off(movie.id)
                messages.success(
                    request,
                    f"“{movie.title}” added — converting it to a playable format in the "
                    f"background. It'll be ready shortly.",
                )
            else:
                messages.success(request, f"“{movie.title}” added to the library.")
            return redirect("catalog:library")
    else:
        form = MovieForm(initial=initial)
    return render(request, "catalog/upload.html", {"form": form})


@login_required
@staff_required
def delete_movie(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    if request.method == "POST":
        title = movie.title
        movie.delete()
        messages.info(request, f"“{title}” removed from the library.")
    return redirect("catalog:library")


def _active_party_for_movie(movie, user):
    """An ongoing watch party already playing this movie, if any.
    Prefers one the user already belongs to."""
    from django.db.models import Q
    from parties.models import WatchParty

    stream = movie.stream_url
    if not stream:
        return None
    qs = WatchParty.objects.filter(
        ended_at__isnull=True, session__video_url__icontains=stream
    ).distinct()
    return qs.filter(Q(host=user) | Q(members__user=user)).first() or qs.first()


@login_required
def watch_movie(request, movie_id):
    """Start (or resume) a watch party for this movie.

    Avoids duplicate parties: if one is already playing this movie, reuse it —
    unless `?new=1` is passed (the modal's "Start a new party" choice)."""
    movie = get_object_or_404(Movie, id=movie_id)
    if not movie.is_playable or movie.is_processing:
        messages.error(request, "That movie isn't ready to play yet.")
        return redirect("catalog:library")

    if not request.GET.get("new"):
        existing = _active_party_for_movie(movie, request.user)
        if existing:
            from parties.models import WatchPartyMember
            WatchPartyMember.objects.get_or_create(party=existing, user=request.user)
            return redirect("parties:room", code=existing.access_code)

    from parties.models import VideoSession, WatchParty, WatchPartyMember
    party = WatchParty.objects.create(
        name=f"{movie.title} night", host=request.user, is_private=True
    )
    WatchPartyMember.objects.create(party=party, user=request.user, is_moderator=True)
    VideoSession.objects.create(
        party=party,
        video_url=request.build_absolute_uri(movie.stream_url),
        subtitle_url=request.build_absolute_uri(movie.subtitle_src) if movie.subtitle_src else "",
        poster_url=request.build_absolute_uri(movie.poster_src) if movie.poster_src else "",
        title=str(movie),
    )
    messages.success(request, f"Party ready — share code {party.access_code}.")
    return redirect("parties:room", code=party.access_code)


@login_required
def movie_detail(request, movie_id):
    """JSON for the fancy detail modal (poster, cast, director, age, etc.)."""
    m = get_object_or_404(Movie, id=movie_id)
    d = m.tmdb_data or {}
    party = _active_party_for_movie(m, request.user)
    return JsonResponse({
        "id": m.id,
        "title": m.title,
        "year": m.year or d.get("year") or "",
        "tagline": d.get("tagline", ""),
        "overview": d.get("overview") or m.description or "",
        "rating": d.get("rating"),
        "runtime": d.get("runtime"),
        "genres": d.get("genres", []),
        "cast": d.get("cast", []),
        "directors": d.get("directors", []),
        "certification": d.get("certification", ""),
        "poster": request.build_absolute_uri(m.poster_src) if m.poster_src else (d.get("poster_url") or ""),
        "backdrop": d.get("backdrop_url") or "",
        "trailer": m.trailer_embed_url,
        "playable": m.is_playable and not m.is_processing,
        "processing": m.is_processing,
        "existing_party": party.access_code if party else "",
    })


@login_required
def tmdb_detail(request, tmdb_id):
    """Same modal shape as movie_detail, but fetched LIVE from TMDb — used for
    trending/search titles that aren't in the library yet. Includes in-library /
    request state so the modal can show Watch / Requested / Request accordingly."""
    media_type = request.GET.get("media_type", "movie")
    d = fetch_tmdb_details(tmdb_id, media_type=media_type)
    if not d:
        return JsonResponse({"error": "Could not load details from TMDb."}, status=502)

    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    req = MovieRequest.objects.filter(tmdb_id=tmdb_id).first()
    party = _active_party_for_movie(movie, request.user) if movie else None
    trailer = f"https://www.youtube.com/embed/{d['trailer_key']}" if d.get("trailer_key") else ""

    return JsonResponse({
        "id": movie.id if movie else None,
        "tmdb_id": tmdb_id,
        "media_type": d.get("media_type", "movie"),
        "title": d.get("title", ""),
        "year": d.get("year", ""),
        "tagline": d.get("tagline", ""),
        "overview": d.get("overview", ""),
        "rating": d.get("rating"),
        "runtime": d.get("runtime"),
        "genres": d.get("genres", []),
        "cast": d.get("cast", []),
        "directors": d.get("directors", []),
        "certification": d.get("certification", ""),
        "poster": (request.build_absolute_uri(movie.poster_src) if movie and movie.poster_src else d.get("poster_url") or ""),
        "backdrop": d.get("backdrop_url") or "",
        "trailer": trailer,
        # library / request / party state
        "tmdb": True,
        "in_library": bool(movie),
        "library_id": movie.id if movie else None,
        "playable": (movie.is_playable and not movie.is_processing) if movie else False,
        "processing": movie.is_processing if movie else False,
        "existing_party": party.access_code if party else "",
        "request_status": req.status if req else None,
    })


@login_required
def movie_status(request, movie_id):
    """Poll endpoint for the background transcode."""
    m = get_object_or_404(Movie, id=movie_id)
    return JsonResponse({
        "status": m.transcode_status,
        "playable": m.is_playable and not m.is_processing,
        "stream_url": request.build_absolute_uri(m.stream_url) if m.is_playable else "",
    })


@login_required
def library_json(request):
    """Playable library movies, for the in-room picker."""
    movies = Movie.objects.all()[:60]
    return JsonResponse({"results": [
        {
            "id": m.id,
            "title": m.title,
            "year": m.year,
            "poster": request.build_absolute_uri(m.poster_src) if m.poster_src else "",
            "stream_url": request.build_absolute_uri(m.stream_url) if m.is_playable else "",
            "subtitle": request.build_absolute_uri(m.subtitle_src) if m.subtitle_src else "",
            "tmdb_id": m.tmdb_id,
            "rating": m.rating,
            "trailer_url": m.trailer_embed_url,
            "overview": (m.tmdb_data or {}).get("overview") or m.description,
        }
        for m in movies if m.is_playable
    ]})


def _request_search_link(req):
    """A 'go get it' search link built from the request's title + year."""
    return req.search_link


def _fetch_poster_bytes(url):
    """Download a poster image. Returns (bytes, ext, mime) or (None, None, None)."""
    if not url:
        return None, None, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lisa/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            ct = (resp.headers.get("Content-Type") or "").lower()
    except Exception:
        return None, None, None
    if "png" in ct:
        return data, "png", "image/png"
    if "webp" in ct:
        return data, "webp", "image/webp"
    return data, "jpg", "image/jpeg"


def _notify_admin_new_request(request, req):
    """Email the sourcing admin when a brand-new, valid TMDb request comes in.

    Includes the TMDb cover both inline (via CID) and as a file attachment.
    No-ops cleanly when SMTP or the notify address isn't configured.
    """
    to_addr = getattr(settings, "MOVIE_REQUEST_NOTIFY_EMAIL", "")
    if not to_addr or not settings.EMAIL_HOST_USER:
        return
    name = f"{req.title} ({req.year})" if req.year else req.title
    get_link = _request_search_link(req)
    tmdb_link = f"https://www.themoviedb.org/movie/{req.tmdb_id}" if req.tmdb_id else ""
    requester = req.requester.get_full_name().strip() if req.requester else ""
    requester = requester or (req.requester.email if req.requester else "someone")

    # Pull the cover from TMDb so we can attach it to the email.
    poster, ext, mime = _fetch_poster_bytes(req.poster_url)

    body = (
        f"New movie request on Lisa.\n\n"
        f"Title: {name}\n"
        f"Requested by: {requester}\n\n"
        f"Go get it: {get_link}\n"
    )
    if tmdb_link:
        body += f"TMDb: {tmdb_link}\n"

    # Inline preview uses the remote TMDb URL (shown when the client loads images);
    # the cover is also attached below so it's always available/saveable.
    poster_html = (
        f'<p><img src="{req.poster_url}" alt="cover" '
        'style="width:160px;border-radius:8px;border:1px solid #ddd;"></p>'
        if req.poster_url else ""
    )
    html = (
        f"<p><b>New movie request on Lisa.</b></p>"
        f"{poster_html}"
        f"<p style='font-size:18px;margin:8px 0;'>{name}</p>"
        f"<p style='color:#555;'>Requested by {requester}</p>"
        f'<p><a href="{get_link}" '
        f'style="display:inline-block;background:#E50914;color:#fff;padding:10px 18px;'
        f'border-radius:6px;text-decoration:none;font-weight:600;">Go get it</a></p>'
        f'<p style="color:#888;font-size:12px;">Search link: {get_link}</p>'
    )
    if tmdb_link:
        html += f'<p style="color:#888;font-size:12px;">TMDb: <a href="{tmdb_link}">{tmdb_link}</a></p>'

    try:
        msg = EmailMultiAlternatives(
            f"[Lisa] Movie request: {name}",
            body,
            settings.DEFAULT_FROM_EMAIL,
            [to_addr],
        )
        msg.attach_alternative(html, "text/html")
        if poster:
            safe = "".join(c for c in name if c.isalnum() or c in " ()-_").strip() or "poster"
            msg.attach(f"{safe}.{ext}", poster, mime)
        msg.send(fail_silently=True)
    except Exception:
        pass


def purge_stale_requests():
    """Delete fulfilled/closed requests older than the retention window.

    Called opportunistically (on the requests dashboard + on new requests) so
    the table self-cleans without a scheduled job; a management command
    (`purge_movie_requests`) is also available for cron.
    """
    days = getattr(settings, "MOVIE_REQUEST_RETENTION_DAYS", 14)
    cutoff = timezone.now() - timedelta(days=days)
    return MovieRequest.objects.filter(
        status__in=("fulfilled", "rejected"), reviewed_at__lt=cutoff
    ).delete()


@login_required
def my_requests(request):
    """A requester's own movie requests, with status, for their dashboard."""
    purge_stale_requests()
    requests = (
        MovieRequest.objects.filter(requester=request.user)
        .select_related("fulfilled_movie")
    )
    return render(request, "catalog/my_requests.html", {"requests": requests})


@login_required
@staff_required
@require_POST
def request_set_status(request, req_id, action):
    """Staff quick-action on a movie request from the admin dashboard."""
    req = get_object_or_404(MovieRequest, id=req_id)
    label = str(req)
    if action == "delete":
        req.delete()
        messages.info(request, f"Deleted request: {label}.")
    else:
        mapping = {"approve": "approved", "reject": "rejected", "fulfill": "fulfilled"}
        status = mapping.get(action)
        if not status:
            messages.error(request, "Unknown action.")
        else:
            req.status = status
            req.reviewed_at = timezone.now()
            req.save(update_fields=["status", "reviewed_at"])
            messages.success(request, f"Marked “{req.title}” {status}.")
    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or "admin_dashboard")


@login_required
@require_POST
def request_movie(request):
    """Create a MovieRequest from a TMDb id (or upvote an existing one)."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
    tmdb_id = payload.get("tmdb_id")
    if not tmdb_id:
        return HttpResponseBadRequest("tmdb_id required")
    media_type = payload.get("media_type", "movie")

    # Already in the library? Tell the client so it can switch to "Watch".
    existing = Movie.objects.filter(tmdb_id=tmdb_id).first()
    if existing:
        return JsonResponse({
            "ok": True, "in_library": True, "library_id": existing.id,
            "quota": user_quota(request.user),
        })

    req = MovieRequest.objects.filter(tmdb_id=tmdb_id).first()
    if req:
        # Idempotent vote — count distinct voters only. Voting doesn't cost
        # quota; only the original requester pays.
        if not req.voters.filter(id=request.user.id).exists():
            req.voters.add(request.user)
            MovieRequest.objects.filter(id=req.id).update(vote_count=F("vote_count") + 1)
            req.refresh_from_db()
        return JsonResponse({
            "ok": True, "request_id": req.id, "vote_count": req.vote_count,
            "voted": True, "status": req.status,
            "quota": user_quota(request.user),
        })

    # Quota gate — block NEW requests once the user is already at their cap.
    # Staff are flagged unlimited=True so this never trips for them.
    q = user_quota(request.user)
    if q["blocked"]:
        return JsonResponse({
            "ok": False,
            "error": "quota_exceeded",
            "message": (
                f"Your server is full — {format_mb(q['used_mb'])} of "
                f"{format_mb(q['limit_mb'])} used. Enough movie requests from you."
            ),
            "quota": q,
        }, status=403)

    # Brand-new request — pull a fresh TMDb snapshot so admins see real metadata.
    details = fetch_tmdb_details(tmdb_id, media_type=media_type) or {}
    req = MovieRequest.objects.create(
        tmdb_id=tmdb_id,
        title=details.get("title") or payload.get("title") or f"TMDb #{tmdb_id}",
        year=details.get("year") or payload.get("year") or "",
        overview=details.get("overview") or payload.get("overview") or "",
        poster_url=details.get("poster_url") or payload.get("poster") or "",
        backdrop_url=details.get("backdrop_url") or "",
        requester=request.user,
        vote_count=1,
        estimated_size_mb=estimate_size_mb(details) if details else estimate_size_mb({}),
    )
    req.voters.add(request.user)

    # Valid TMDb movie (we got real details back) → alert the sourcing admin.
    if details:
        _notify_admin_new_request(request, req)
    purge_stale_requests()

    return JsonResponse({
        "ok": True, "request_id": req.id, "vote_count": req.vote_count,
        "voted": True, "status": req.status,
        "quota": user_quota(request.user),
    })


@login_required
def quota_status(request):
    """JSON snapshot of the caller's quota — drives the nav chip & UI gates."""
    return JsonResponse(user_quota(request.user))
