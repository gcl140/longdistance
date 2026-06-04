"""Range-aware media serving so the <video> player can seek.

Django's built-in static `serve`/`FileResponse` ignore the HTTP `Range` header,
which makes seeking in a large video hang. This view honours `Range` and returns
`206 Partial Content`, so scrubbing/skipping works for uploaded media.
For production, serve media via Nginx/your media server instead.
"""

import mimetypes
import os
import re

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404, StreamingHttpResponse
from django.utils._os import safe_join

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")
_CHUNK = 8192

# Browsers reject WebVTT subtitle tracks unless served as text/vtt.
mimetypes.add_type("text/vtt", ".vtt")


def _iter_file(path, start, length):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            data = f.read(min(_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def serve_media(request, path):
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except (ValueError, SuspiciousFileOperation):
        raise Http404()
    if not os.path.isfile(full):
        raise Http404("Not found")

    size = os.path.getsize(full)
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    range_header = request.META.get("HTTP_RANGE", "").strip()
    m = _RANGE_RE.match(range_header) if range_header else None

    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        start = min(start, end)
        length = end - start + 1
        resp = StreamingHttpResponse(
            _iter_file(full, start, length), status=206, content_type=ctype
        )
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(length)
    else:
        resp = StreamingHttpResponse(_iter_file(full, 0, size), content_type=ctype)
        resp["Content-Length"] = str(size)

    resp["Accept-Ranges"] = "bytes"
    return resp
