"""EXIF capture-time extraction.

Shared by the upload path (`POST /manual-photos`) and the repair script
(`scripts/fix_timestamps.py`) so the parsing rules — notably the trailing-NUL
handling on Pixel/Google strings — can never diverge between the two.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Union

from PIL import Image
from PIL.ExifTags import TAGS

class _NoOffset:
    """Sentinel type for `NO_OFFSET`; identity comparison avoids string fragility."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "NO_OFFSET"


# Returned in place of a datetime when DateTimeOriginal exists but carries no UTC
# offset: the wall-clock time is ambiguous, so callers must decide how to handle
# it rather than us guessing (assuming UTC would corrupt non-UTC photos). Compare
# with `result is NO_OFFSET`.
NO_OFFSET = _NoOffset()

ExifSource = Union[bytes, bytearray, str, Path]


def _parse_offset(raw: str) -> timezone:
    """Parse an EXIF offset string (`±HH:MM` or `±HHMM`) into a tzinfo.

    Raises ``ValueError`` for anything that isn't a signed numeric offset (e.g.
    ``Z``, ``UTC``, empty) so the caller treats it as unparseable rather than
    silently producing a wrong timezone.
    """
    raw = raw.replace("\x00", "").strip()
    if not raw or raw[0] not in "+-":
        raise ValueError(f"unrecognised EXIF offset: {raw!r}")
    sign = -1 if raw[0] == "-" else 1
    body = raw[1:]
    hours, _, minutes = body.partition(":") if ":" in body else (body[:2], "", body[2:])
    return timezone(timedelta(hours=sign * int(hours), minutes=sign * int(minutes or 0)))


def read_exif_captured_at(source: ExifSource):
    """Return the capture instant from EXIF.

    Returns a timezone-aware UTC ``datetime`` when DateTimeOriginal and a UTC
    offset are both present, the ``NO_OFFSET`` sentinel when DateTimeOriginal is
    present but the offset is absent or unparseable, or ``None`` when there is no
    usable EXIF / DateTimeOriginal or the data cannot be parsed.
    """
    try:
        src = BytesIO(bytes(source)) if isinstance(source, (bytes, bytearray)) else source
        with Image.open(src) as opened:
            exif = opened.getexif()
        if not exif:
            return None

        # DateTimeOriginal and offset tags live in the Exif sub-IFD (0x8769);
        # merge it so they're accessible alongside the root IFD tags.
        merged = dict(exif)
        merged.update(exif.get_ifd(0x8769))
        tags = {TAGS.get(k, k): v for k, v in merged.items()}
        dto_raw = tags.get("DateTimeOriginal")
        if not dto_raw:
            return None

        offset_raw = tags.get("OffsetTimeOriginal") or tags.get("OffsetTime")
        # Pixel/Google strings carry a trailing NUL that str.strip() leaves in
        # place, so drop it explicitly before parsing.
        dt = datetime.strptime(dto_raw.replace("\x00", "").strip(), "%Y:%m:%d %H:%M:%S")

        if not offset_raw:
            return NO_OFFSET

        try:
            tzinfo = _parse_offset(offset_raw)
        except ValueError:
            # DateTimeOriginal is real but the offset is junk — treat as ambiguous
            # rather than guessing UTC.
            return NO_OFFSET

        return dt.replace(tzinfo=tzinfo).astimezone(timezone.utc)
    except Exception:
        return None
