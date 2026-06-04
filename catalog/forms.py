from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Movie
from .subtitles import decode_subtitle_bytes, srt_to_vtt


class MovieForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = [
            "title", "year", "description",
            "video_file", "video_url",
            "subtitle_file", "subtitle_url",
            "poster", "poster_url", "tmdb_id",
        ]

    def clean_subtitle_file(self):
        f = self.cleaned_data.get("subtitle_file")
        if not f or not f.name.lower().endswith(".srt"):
            return f
        text = srt_to_vtt(decode_subtitle_bytes(f.read()))
        return SimpleUploadedFile(
            f.name[:-4] + ".vtt", text.encode("utf-8"), content_type="text/vtt"
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("video_file") and not cleaned.get("video_url"):
            raise forms.ValidationError("Provide a video file or a video URL.")
        return cleaned
