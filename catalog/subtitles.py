"""SRT → WebVTT conversion.

Browsers only load WebVTT into <track>; uploaded .srt files are silently ignored.
We normalise everything to .vtt on the way in.
"""

import re

_TS_RE = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(text: str) -> str:
    """Convert SRT subtitle text to WebVTT. Idempotent if already VTT."""
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.lstrip().startswith("WEBVTT"):
        return text
    # SRT timestamps use a comma before milliseconds; VTT uses a period.
    text = _TS_RE.sub(r"\1.\2", text)
    # Drop SRT cue-index lines (a bare number sitting above a timestamp line).
    lines = text.split("\n")
    cleaned = []
    for i, line in enumerate(lines):
        if line.strip().isdigit() and i + 1 < len(lines) and "-->" in lines[i + 1]:
            continue
        cleaned.append(line)
    return "WEBVTT\n\n" + "\n".join(cleaned).lstrip("\n")


def decode_subtitle_bytes(raw: bytes) -> str:
    """Decode subtitle bytes, tolerating BOM and non-UTF-8 SRT files."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")
