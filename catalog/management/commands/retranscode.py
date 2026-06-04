"""Re-run movie transcoding from the command line.

Usage:
    python manage.py retranscode            # resume everything stuck in "processing"
    python manage.py retranscode 12         # re-run a specific movie id
    python manage.py retranscode --failed   # retry everything marked "failed"

Runs synchronously (in the foreground) so you can watch ffmpeg's progress and
exit codes — handy when a conversion looked stuck and you want to see why.
"""

from django.core.management.base import BaseCommand

from catalog.models import Movie
from catalog import transcode


class Command(BaseCommand):
    help = "Re-run movie -> MP4 transcoding (stuck, failed, or a specific id)."

    def add_arguments(self, parser):
        parser.add_argument("movie_id", nargs="?", type=int, default=None)
        parser.add_argument(
            "--failed", action="store_true",
            help="Retry every movie whose status is 'failed'.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Re-encode even already-playable files (e.g. upgrade old MP4s "
                 "to an HLS ladder). Files that are already HLS are still skipped.",
        )

    def handle(self, *args, **opts):
        ff = transcode.get_ffmpeg()
        if not ff:
            self.stderr.write("No working ffmpeg found (system or imageio-ffmpeg).")
            return
        self.stdout.write(f"Using ffmpeg: {ff}")

        if opts["movie_id"]:
            qs = Movie.objects.filter(id=opts["movie_id"])
        elif opts["failed"]:
            qs = Movie.objects.filter(transcode_status="failed")
        else:
            qs = Movie.objects.filter(transcode_status="processing")

        movies = list(qs)
        if not movies:
            self.stdout.write("Nothing to do.")
            return

        for movie in movies:
            name = movie.video_file.name if movie.video_file else ""
            if not name:
                self.stdout.write(f"  movie {movie.id}: no file, skipping")
                continue
            already_hls = name.lower().endswith(".m3u8")
            if already_hls or (not opts["force"] and not transcode.needs_transcode(name)):
                movie.transcode_status = "ready"
                movie.save(update_fields=["transcode_status"])
                why = "already HLS" if already_hls else "already playable"
                self.stdout.write(f"  movie {movie.id}: {why}, marked ready (use --force to re-encode)")
                continue
            self.stdout.write(f"  movie {movie.id}: transcoding {name} ...")
            movie.transcode_status = "processing"
            movie.save(update_fields=["transcode_status"])
            transcode._run(movie.id)  # synchronous: blocks until ffmpeg finishes
            movie.refresh_from_db()
            self.stdout.write(f"  movie {movie.id}: -> {movie.transcode_status}")

        self.stdout.write(self.style.SUCCESS("Done."))
