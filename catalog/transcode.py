"""Background MP4 transcoding for uploaded movies.

Browsers reliably play only MP4/WebM with a handful of codecs (H.264/VP9/AV1).
When a user uploads something else (e.g. an MKV, or HEVC), we keep the original
so the movie isn't blocked, transcode to a browser-friendly MP4 in a background
thread, then atomically repoint the Movie at the MP4 and delete the original.

ffmpeg resolution: use a working system `ffmpeg` if present, otherwise fall back
to the self-contained binary shipped by the `imageio-ffmpeg` package — so this
works even if ffmpeg "isn't installed" on the box.

For a real multi-process deployment, move this to Celery/RQ. A daemon thread is
fine for the single-process self-hosted setup.
"""

import os
import shutil
import subprocess
import threading

# Containers/codecs browsers play natively — anything else gets transcoded.
GOOD_EXTS = {".mp4", ".m4v", ".webm"}

_ffmpeg_cache = None


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


def needs_transcode(filename):
    """Cheap, extension-based check — MKV/AVI/etc. need converting."""
    return os.path.splitext(filename or "")[1].lower() not in GOOD_EXTS


def _transcode_to_mp4(src, ff):
    """Transcode `src` to a sibling .mp4 (H.264/AAC, faststart). Returns its path."""
    base, _ = os.path.splitext(src)
    tmp_out = base + ".converting.mp4"
    final_out = base + ".mp4"
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-map", "0:v:0", "-map", "0:a:0?",          # first video + audio (if any)
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        tmp_out,
    ]
    subprocess.run(cmd, check=True)
    os.replace(tmp_out, final_out)  # atomic within same dir
    return final_out


def kick_off(movie_id):
    """Start the background transcode for a movie (non-blocking)."""
    threading.Thread(target=_run, args=(movie_id,), daemon=True).start()


def _run(movie_id):
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
        try:
            out = _transcode_to_mp4(src, ff)
        except Exception:
            movie.transcode_status = "failed"
            movie.save(update_fields=["transcode_status"])
            return

        # Repoint the model at the new MP4 (path relative to MEDIA_ROOT).
        from django.conf import settings
        new_rel = os.path.relpath(out, settings.MEDIA_ROOT)
        movie.video_file.name = new_rel
        movie.transcode_status = "ready"
        movie.save(update_fields=["video_file", "transcode_status"])

        # Delete the original unplayable file to reclaim storage.
        if os.path.abspath(src) != os.path.abspath(out) and os.path.exists(src):
            try:
                os.remove(src)
            except OSError:
                pass
    finally:
        connections.close_all()  # don't leak this thread's DB connection
