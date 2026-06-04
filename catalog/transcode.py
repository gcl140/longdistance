"""Background transcoding for uploaded movies.

Browsers reliably play only MP4/WebM with a handful of codecs (H.264/VP9/AV1).
When a user uploads something else (e.g. an MKV, or HEVC), we keep the original
so the movie isn't blocked, transcode it in a background thread, then atomically
repoint the Movie at the output and delete the original.

Output is an **HLS adaptive-bitrate ladder** (a `master.m3u8` pointing at a few
renditions). The player picks the rung that fits each viewer's bandwidth, so a
slow connection drops to a lower quality instead of buffering — the fix for the
"lags when watching remotely" problem. If HLS generation fails for any reason we
fall back to a single browser-friendly MP4 so the movie is still playable.

ffmpeg resolution: use a working system `ffmpeg`/`ffprobe` if present, otherwise
fall back to the self-contained binary shipped by `imageio-ffmpeg` (which has no
ffprobe — we degrade to sensible defaults in that case).

For a real multi-process deployment, move this to Celery/RQ. A daemon thread is
fine for the single-process self-hosted setup.
"""

import os
import shutil
import subprocess
import threading

# Containers/codecs the player handles without transcoding (.m3u8 = already HLS).
GOOD_EXTS = {".mp4", ".m4v", ".webm", ".m3u8"}

# HLS bitrate ladder, highest first: (height, video kbps, audio kbps). We cap the
# top rung at 720p — a single old box can't stream multiple 1080p renditions, and
# 1080p is exactly what chokes a home uplink. Rungs above the source are skipped
# (no upscaling); at most 3 rungs are kept so the one-time encode stays bounded.
_LADDER = [
    (720, 2800, 128),
    (480, 1400, 128),
    (360, 800, 96),
]

_ffmpeg_cache = None
_ffprobe_cache = None


def get_ffmpeg():
    """Return a path to a working ffmpeg, or None if none can be found."""
    global _ffmpeg_cache
    if _ffmpeg_cache is not None:
        return _ffmpeg_cache or None

    candidates = []
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        candidates.append(sys_ff)
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    for ff in candidates:
        try:
            subprocess.run([ff, "-version"], capture_output=True, timeout=15, check=True)
            _ffmpeg_cache = ff
            return ff
        except Exception:
            continue

    _ffmpeg_cache = ""  # cache the failure
    return None


def get_ffprobe():
    """Return a path to ffprobe (sibling of system ffmpeg), or None.

    imageio-ffmpeg ships no ffprobe, so this is None when only that fallback
    exists — callers must cope (we just assume defaults for resolution/audio)."""
    global _ffprobe_cache
    if _ffprobe_cache is not None:
        return _ffprobe_cache or None

    candidates = []
    sys_fp = shutil.which("ffprobe")
    if sys_fp:
        candidates.append(sys_fp)
    ff = get_ffmpeg()  # try a sibling next to whatever ffmpeg we resolved
    if ff:
        guess = os.path.join(os.path.dirname(ff), "ffprobe")
        if guess not in candidates and os.path.exists(guess):
            candidates.append(guess)

    for fp in candidates:
        try:
            subprocess.run([fp, "-version"], capture_output=True, timeout=15, check=True)
            _ffprobe_cache = fp
            return fp
        except Exception:
            continue

    _ffprobe_cache = ""
    return None


def _probe_height(src, ffprobe):
    """Source video height in pixels, or None if it can't be determined."""
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", src],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip().splitlines()
        return int(out[0]) if out and out[0] else None
    except Exception:
        return None


def _has_audio(src, ffprobe):
    """True if the source has at least one audio stream (assume yes if unknown)."""
    if not ffprobe:
        return True
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=index", "-of", "csv=p=0", src],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        return bool(out)
    except Exception:
        return True


def _build_ladder(height):
    """Pick the ladder rungs at or below the source height (max 3)."""
    rungs = [r for r in _LADDER if not height or r[0] <= height]
    if not rungs:                 # source smaller than the lowest rung
        rungs = [_LADDER[-1]]
    return rungs[:3]


def _transcode_to_hls(src, ff, ffprobe):
    """Transcode `src` into an HLS ladder under `<base>_hls/`.

    Returns the path to the master playlist. Raises on ffmpeg failure so the
    caller can fall back to a plain MP4."""
    base, _ = os.path.splitext(src)
    out_dir = base + "_hls"
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    rungs = _build_ladder(_probe_height(src, ffprobe))
    has_audio = _has_audio(src, ffprobe)
    n = len(rungs)

    # Share CPU across all rungs so we don't oversubscribe the box.
    cores = os.cpu_count() or 2
    threads = str(max(1, cores // max(1, n)))

    # split the source video into n streams, scale each to its rung height
    # (-2 keeps the aspect ratio and an even width that H.264 requires).
    split = f"[0:v]split={n}" + "".join(f"[v{i}]" for i in range(n)) + ";"
    scales = ";".join(f"[v{i}]scale=-2:{h}[v{i}o]" for i, (h, _, _) in enumerate(rungs))

    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error", "-threads", threads,
        "-i", src,
        "-filter_complex", split + scales,
    ]
    var_map = []
    for i, (_, vk, ak) in enumerate(rungs):
        cmd += ["-map", f"[v{i}o]"]
        if has_audio:
            cmd += ["-map", "0:a:0"]
        cmd += [
            f"-b:v:{i}", f"{vk}k",
            f"-maxrate:v:{i}", f"{int(vk * 1.07)}k",
            f"-bufsize:v:{i}", f"{vk * 2}k",
        ]
        if has_audio:
            cmd += [f"-b:a:{i}", f"{ak}k"]
        var_map.append(f"v:{i},a:{i}" if has_audio else f"v:{i}")

    cmd += [
        # Constant GOP so segment boundaries line up across renditions (clean
        # quality switches). 48 frames ≈ 2s at 24fps; 6s segments = 3 GOPs.
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-g", "48", "-keyint_min", "48", "-sc_threshold", "0",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-ac", "2"]
    cmd += [
        # Flat layout: master.m3u8 + prog_<rung>.m3u8 + seg_<rung>_<n>.ts, all in
        # out_dir. Master URIs are relative, so the whole folder is portable.
        "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", os.path.join(out_dir, "seg_%v_%05d.ts"),
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", " ".join(var_map),
        os.path.join(out_dir, "prog_%v.m3u8"),
    ]
    if shutil.which("nice"):
        cmd = ["nice", "-n", "15"] + cmd

    subprocess.run(cmd, check=True)
    master = os.path.join(out_dir, "master.m3u8")
    if not os.path.exists(master):
        raise RuntimeError("HLS master playlist was not produced")
    return master


def needs_transcode(filename):
    """Cheap, extension-based check — MKV/AVI/etc. need converting."""
    return os.path.splitext(filename or "")[1].lower() not in GOOD_EXTS


def _transcode_to_mp4(src, ff):
    """Transcode `src` to a sibling .mp4 (H.264/AAC, faststart). Returns its path."""
    base, _ = os.path.splitext(src)
    tmp_out = base + ".converting.mp4"
    final_out = base + ".mp4"

    # Cap ffmpeg to (cores - 1) threads and run it at low CPU priority so the
    # web server, Postgres, and Redis stay responsive on a single small box —
    # otherwise a long transcode pegs every core and requests start 500ing.
    cores = os.cpu_count() or 2
    threads = str(max(1, cores - 1))
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-threads", threads,
        "-i", src,
        "-map", "0:v:0", "-map", "0:a:0?",          # first video + audio (if any)
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        tmp_out,
    ]
    # `nice` lowers CPU priority; only prepend it if available (Linux/macOS).
    if shutil.which("nice"):
        cmd = ["nice", "-n", "15"] + cmd

    subprocess.run(cmd, check=True)
    os.replace(tmp_out, final_out)  # atomic within same dir
    return final_out


def kick_off(movie_id):
    """Start the background transcode for a movie (non-blocking)."""
    threading.Thread(target=_run, args=(movie_id,), daemon=True).start()


def _run(movie_id):
    from django.conf import settings
    from django.db import connections
    from .models import Movie

    try:
        movie = Movie.objects.get(id=movie_id)
        ff = get_ffmpeg()
        if not ff or not movie.video_file:
            movie.transcode_status = "failed" if not ff else "ready"
            movie.save(update_fields=["transcode_status"])
            return

        src = movie.video_file.path

        # Prefer an HLS ladder (adaptive bitrate); if anything goes wrong, fall
        # back to a single MP4 so the movie is at least playable.
        out = None
        try:
            out = _transcode_to_hls(src, ff, get_ffprobe())
        except Exception as e:
            print(f"[transcode] HLS failed for movie {movie.id} ({e}); falling back to MP4")
            try:
                out = _transcode_to_mp4(src, ff)
            except Exception as e2:
                print(f"[transcode] MP4 fallback also failed for movie {movie.id}: {e2}")
                movie.transcode_status = "failed"
                movie.save(update_fields=["transcode_status"])
                return

        # Repoint the model at the new output (path relative to MEDIA_ROOT). For
        # HLS this is the master.m3u8; the player detects the extension.
        new_rel = os.path.relpath(out, settings.MEDIA_ROOT)
        movie.video_file.name = new_rel
        movie.transcode_status = "ready"
        movie.save(update_fields=["video_file", "transcode_status"])

        # Delete the original unplayable file to reclaim storage.
        if os.path.abspath(src) != os.path.abspath(out) and os.path.isfile(src):
            try:
                os.remove(src)
            except OSError:
                pass
    finally:
        connections.close_all()  # don't leak this thread's DB connection


def resume_stuck():
    """Re-kick any conversions left in "processing" (e.g. interrupted by a
    server restart). Movies whose file no longer needs transcoding are just
    marked ready. Safe to call repeatedly; logs what it does to stdout."""
    from django.db import connections
    from .models import Movie

    try:
        stuck = list(Movie.objects.filter(transcode_status="processing"))
        for movie in stuck:
            name = movie.video_file.name if movie.video_file else ""
            if not name:
                continue
            if needs_transcode(name):
                print(f"[transcode] resuming stuck conversion: movie {movie.id} ({name})")
                kick_off(movie.id)
            else:
                movie.transcode_status = "ready"
                movie.save(update_fields=["transcode_status"])
                print(f"[transcode] movie {movie.id} already playable, marked ready")
    except Exception as e:
        print(f"[transcode] resume_stuck skipped: {e}")
    finally:
        connections.close_all()
