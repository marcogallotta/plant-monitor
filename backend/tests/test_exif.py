from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from app.exif import NO_OFFSET, read_exif_captured_at


def _jpeg(dto=None, offset=None):
    """Build a minimal JPEG, optionally with EXIF DateTimeOriginal / OffsetTimeOriginal."""
    img = Image.new("RGB", (8, 8), "green")
    buf = BytesIO()
    if dto is None:
        img.save(buf, "jpeg")
    else:
        exif = Image.Exif()
        ifd = exif.get_ifd(0x8769)
        ifd[0x9003] = dto  # DateTimeOriginal
        if offset is not None:
            ifd[0x9011] = offset  # OffsetTimeOriginal
        img.save(buf, "jpeg", exif=exif)
    return buf.getvalue()


def test_returns_utc_datetime_with_offset():
    result = read_exif_captured_at(_jpeg("2026:05:08 07:30:00", "+02:00"))
    assert result == datetime(2026, 5, 8, 5, 30, 0, tzinfo=timezone.utc)


def test_handles_negative_offset():
    result = read_exif_captured_at(_jpeg("2026:05:08 07:30:00", "-03:00"))
    assert result == datetime(2026, 5, 8, 10, 30, 0, tzinfo=timezone.utc)


def test_handles_minute_offset():
    result = read_exif_captured_at(_jpeg("2026:05:08 07:30:00", "+02:30"))
    assert result == datetime(2026, 5, 8, 5, 0, 0, tzinfo=timezone.utc)


def test_malformed_offset_returns_no_offset_sentinel():
    # "Z"/"UTC" etc. are not signed numeric offsets — don't guess, don't crash.
    for junk in ("Z", "UTC", ""):
        assert read_exif_captured_at(_jpeg("2026:05:08 07:30:00", junk)) is NO_OFFSET


def test_strips_trailing_nul_byte():
    # Pixel/Google strings carry a trailing NUL — must still parse.
    result = read_exif_captured_at(_jpeg("2026:05:08 07:30:00\x00", "+02:00\x00"))
    assert result == datetime(2026, 5, 8, 5, 30, 0, tzinfo=timezone.utc)


def test_no_offset_returns_sentinel():
    assert read_exif_captured_at(_jpeg("2026:05:08 07:30:00")) == NO_OFFSET


def test_no_exif_returns_none():
    assert read_exif_captured_at(_jpeg()) is None


def test_garbage_bytes_returns_none():
    assert read_exif_captured_at(b"FAKEIMAGE") is None
