from django.conf import settings
from django.db import models

# TMDb's canonical movie genres, in their conventional order. Used to order the
# library's genre filter consistently (genres not in this list sort after, A–Z).
TMDB_MOVIE_GENRES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western",
]


class Movie(models.Model):
    """A movie/show in the Lisa library — the bridge between TMDb metadata and
    an actual playable file (uploaded here, or a URL on your media server).
    """

    title = models.CharField(max_length=255)
    year = models.CharField(max_length=8, blank=True)
    description = models.TextField(blank=True)

    # Playable source — EITHER an uploaded file OR an external URL (.mp4/.m3u8).
    video_file = models.FileField(upload_to="movies/", blank=True, null=True)
    video_url = models.URLField(blank=True, help_text="External stream URL if not uploading a file")

    # Subtitles (WebVTT). Uploaded file wins, else an external URL.
    subtitle_file = models.FileField(upload_to="subtitles/", blank=True, null=True)
    subtitle_url = models.URLField(blank=True, help_text="External .vtt URL")

    # Artwork — uploaded poster wins, else a TMDb poster URL.
    poster = models.ImageField(upload_to="posters/", blank=True, null=True)
    poster_url = models.URLField(blank=True)

    tmdb_id = models.IntegerField(null=True, blank=True, db_index=True)
    # Snapshot of TMDb metadata at the time the movie was added. Keys we rely on:
    #   title, year, overview, rating, vote_count, poster_path, backdrop_path,
    #   runtime, genres (list of names), trailer_key (YouTube id), tagline.
    tmdb_data = models.JSONField(default=dict, blank=True)

    TRANSCODE_CHOICES = [
        ("ready", "Ready"),
        ("processing", "Processing"),
        ("failed", "Failed"),
    ]
    transcode_status = models.CharField(
        max_length=12, choices=TRANSCODE_CHOICES, default="ready"
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movies_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title}{f' ({self.year})' if self.year else ''}"

    @property
    def stream_url(self):
        """The URL the player should load."""
        if self.video_file:
            return self.video_file.url
        return self.video_url

    @property
    def poster_src(self):
        if self.poster:
            return self.poster.url
        return self.poster_url

    @property
    def subtitle_src(self):
        if self.subtitle_file:
            return self.subtitle_file.url
        return self.subtitle_url

    @property
    def is_playable(self):
        return bool(self.video_file or self.video_url)

    @property
    def is_processing(self):
        return self.transcode_status == "processing"

    @property
    def trailer_embed_url(self):
        key = (self.tmdb_data or {}).get("trailer_key")
        return f"https://www.youtube.com/embed/{key}" if key else ""

    @property
    def rating(self):
        return (self.tmdb_data or {}).get("rating")

    @property
    def genre_list(self):
        """Genre names from the TMDb snapshot (empty list if none)."""
        return [g for g in (self.tmdb_data or {}).get("genres", []) if g]


class MovieRequest(models.Model):
    """A user-submitted ask for a movie that isn't in the library yet.

    Identified by tmdb_id when possible (so duplicate requests collapse).
    Multiple users can vote via the M2M; vote_count is denormalised for sorting.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("fulfilled", "Fulfilled"),
    ]

    tmdb_id = models.IntegerField(null=True, blank=True, unique=True)
    title = models.CharField(max_length=255)
    year = models.CharField(max_length=8, blank=True)
    overview = models.TextField(blank=True)
    poster_url = models.URLField(blank=True)
    backdrop_url = models.URLField(blank=True)

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movie_requests",
    )
    voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="movie_requests_voted",
        blank=True,
    )
    vote_count = models.PositiveIntegerField(default=1, db_index=True)
    # Estimated download size in MB, captured at request time from tmdb_data.runtime.
    # Used to enforce the per-user 5GB request quota — see catalog/quota.py.
    estimated_size_mb = models.PositiveIntegerField(default=0, db_index=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    fulfilled_movie = models.ForeignKey(
        "Movie", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True, help_text="Optional admin notes")

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-vote_count", "-created_at"]

    def __str__(self):
        return f"{self.title}{f' ({self.year})' if self.year else ''} — {self.status}"

    @property
    def search_link(self):
        """A 'go get it' search link built from the title + year."""
        import urllib.parse

        from django.conf import settings
        query = f"{self.title} {self.year}".strip()
        return settings.TORRENT_SEARCH_URL.format(query=urllib.parse.quote_plus(query))
