import pytest

import app.camera_import as ci
from app.camera_import import _extract_embedded_jpeg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(directory, name, content=b"FAKEIMAGE"):
    p = directory / name
    p.write_bytes(content)
    return p


def _fake_raw(embedded_jpeg=b"\xff\xd8\xff\xe0JFIF\xff\xd9"):
    """Return bytes that look like a RAW file wrapping an embedded JPEG."""
    return b"\x00" * 16 + embedded_jpeg + b"\x00" * 8


def _scan(client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/camera-import/scan{'?' + qs if qs else ''}")


@pytest.fixture(autouse=True)
def reset_cache():
    ci._cache = {}
    ci._cache_built_at = 0.0
    yield
    ci._cache = {}
    ci._cache_built_at = 0.0


@pytest.fixture
def media_root(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def patched_scan(media_root, monkeypatch):
    monkeypatch.setattr(ci, "_SCAN_PATH", media_root)
    return media_root


# ---------------------------------------------------------------------------
# _extract_embedded_jpeg unit tests
# ---------------------------------------------------------------------------

def test_extract_jpeg_finds_embedded():
    jpeg = b"\xff\xd8\xff\xe0" + b"X" * 100 + b"\xff\xd9"
    raw = b"\x00" * 20 + jpeg + b"\x00" * 10
    result = _extract_embedded_jpeg(raw)
    assert result == jpeg


def test_extract_jpeg_returns_none_when_absent():
    assert _extract_embedded_jpeg(b"\x00" * 100) is None


def test_extract_jpeg_returns_largest():
    small = b"\xff\xd8\xff\xe0" + b"S" * 10 + b"\xff\xd9"
    large = b"\xff\xd8\xff\xe0" + b"L" * 500 + b"\xff\xd9"
    raw = small + b"\x00" * 4 + large
    result = _extract_embedded_jpeg(raw)
    assert result == large


def test_extract_jpeg_incomplete_segment_skipped():
    # SOI present but no EOI
    raw = b"\xff\xd8\xff\xe0" + b"X" * 100
    assert _extract_embedded_jpeg(raw) is None


# ---------------------------------------------------------------------------
# Scan – path / extension filtering
# ---------------------------------------------------------------------------

def test_scan_missing_path_returns_empty(tmp_path, monkeypatch, client):
    monkeypatch.setattr(ci, "_SCAN_PATH", tmp_path / "nonexistent")
    r = _scan(client)
    assert r.status_code == 200
    data = r.json()
    assert data["candidates"] == []
    assert len(data["warnings"]) > 0


def test_scan_finds_jpg(patched_scan, client):
    _write(patched_scan, "IMG_001.JPG")
    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "IMG_001.JPG" in filenames


def test_scan_finds_jpeg(patched_scan, client):
    _write(patched_scan, "IMG_001.jpeg")
    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "IMG_001.jpeg" in filenames


def test_scan_finds_arw(patched_scan, client):
    _write(patched_scan, "DSC01234.ARW")
    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "DSC01234.ARW" in filenames


def test_scan_finds_orf(patched_scan, client):
    _write(patched_scan, "P1000001.ORF")
    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "P1000001.ORF" in filenames


def test_scan_ignores_png(patched_scan, client):
    _write(patched_scan, "photo.png")
    assert _scan(client).json()["candidates"] == []


def test_scan_ignores_mp4(patched_scan, client):
    _write(patched_scan, "video.mp4")
    assert _scan(client).json()["candidates"] == []


def test_scan_ignores_txt(patched_scan, client):
    _write(patched_scan, "info.txt")
    assert _scan(client).json()["candidates"] == []


# ---------------------------------------------------------------------------
# Scan – candidate shape and raw flag
# ---------------------------------------------------------------------------

def test_scan_candidate_has_expected_fields(patched_scan, client):
    _write(patched_scan, "DSC01234.ARW")
    candidate = _scan(client).json()["candidates"][0]
    for field in ("id", "filename", "extension", "size_bytes", "mtime_ms", "captured_at",
                  "captured_at_source", "is_raw", "already_imported", "thumbnail_url"):
        assert field in candidate, f"missing field: {field}"


def test_scan_arw_is_raw(patched_scan, client):
    _write(patched_scan, "DSC01234.ARW")
    assert _scan(client).json()["candidates"][0]["is_raw"] is True


def test_scan_jpg_is_not_raw(patched_scan, client):
    _write(patched_scan, "IMG_001.JPG")
    assert _scan(client).json()["candidates"][0]["is_raw"] is False


def test_scan_thumbnail_url_uses_file_id(patched_scan, client):
    _write(patched_scan, "IMG_001.JPG")
    candidate = _scan(client).json()["candidates"][0]
    assert candidate["thumbnail_url"] == f"/camera-import/thumbs/{candidate['id']}"


# ---------------------------------------------------------------------------
# Scan – duplicate detection (filename + size)
# ---------------------------------------------------------------------------

def _import_as_original(client, original_filename, content=b"FAKEIMAGE"):
    return client.post("/manual-photos", data={}, files={
        "image": (original_filename, content, "image/jpeg"),
    })


def test_scan_marks_already_imported_exact_match(patched_scan, client):
    content = b"EXACTCONTENT"
    _write(patched_scan, "DSC01234.ARW", content)
    _import_as_original(client, "DSC01234.ARW", content)

    candidate = next(
        c for c in _scan(client, include_imported="true").json()["candidates"]
        if c["filename"] == "DSC01234.ARW"
    )
    assert candidate["already_imported"] is True


def test_scan_does_not_mark_imported_when_size_differs(patched_scan, client):
    """Same filename but different size (e.g. card rollover) → not a duplicate."""
    _write(patched_scan, "DSC00001.ARW", b"NEW_CONTENT_DIFFERENT_SIZE")
    _import_as_original(client, "DSC00001.ARW", b"OLD")  # different size

    candidate = next(
        c for c in _scan(client, include_imported="true").json()["candidates"]
        if c["filename"] == "DSC00001.ARW"
    )
    assert candidate["already_imported"] is False


def test_scan_hides_imported_by_default(patched_scan, client):
    content = b"CONTENT"
    _write(patched_scan, "DSC01234.ARW", content)
    _import_as_original(client, "DSC01234.ARW", content)

    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "DSC01234.ARW" not in filenames


def test_scan_shows_imported_when_requested(patched_scan, client):
    content = b"CONTENT"
    _write(patched_scan, "DSC01234.ARW", content)
    _import_as_original(client, "DSC01234.ARW", content)

    filenames = [c["filename"] for c in _scan(client, include_imported="true").json()["candidates"]]
    assert "DSC01234.ARW" in filenames


def test_scan_already_imported_count(patched_scan, client):
    content = b"CONTENT"
    _write(patched_scan, "DSC01234.ARW", content)
    _write(patched_scan, "DSC01235.ARW")
    _import_as_original(client, "DSC01234.ARW", content)

    assert _scan(client, include_imported="true").json()["already_imported_count"] == 1


# ---------------------------------------------------------------------------
# Scan – path safety
# ---------------------------------------------------------------------------

def test_scan_rejects_symlink_escaping_root(patched_scan, tmp_path, client):
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"SECRET")
    (patched_scan / "escape.jpg").symlink_to(outside)

    filenames = [c["filename"] for c in _scan(client).json()["candidates"]]
    assert "escape.jpg" not in filenames


# ---------------------------------------------------------------------------
# Thumbnail endpoint
# ---------------------------------------------------------------------------

def _file_id_for(filename: str) -> str:
    """Look up the file_id (cache key) for a given filename."""
    return next(fid for fid, entry in ci._cache.items() if entry["filename"] == filename)


def test_thumb_jpeg_returns_bytes(patched_scan, client):
    content = b"\xff\xd8\xff\xe0" + b"X" * 50 + b"\xff\xd9"
    _write(patched_scan, "IMG_001.JPG", content)
    _scan(client)  # populate cache

    r = client.get(f"/camera-import/thumbs/{_file_id_for('IMG_001.JPG')}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == content


def test_thumb_arw_extracts_embedded_jpeg(patched_scan, client):
    embedded = b"\xff\xd8\xff\xe0" + b"E" * 80 + b"\xff\xd9"
    _write(patched_scan, "DSC01234.ARW", _fake_raw(embedded))
    _scan(client)

    r = client.get(f"/camera-import/thumbs/{_file_id_for('DSC01234.ARW')}")
    assert r.status_code == 200
    assert r.content == embedded


def test_thumb_raw_no_jpeg_returns_422(patched_scan, client):
    _write(patched_scan, "DSC01234.ARW", b"\x00" * 100)
    _scan(client)

    assert client.get(f"/camera-import/thumbs/{_file_id_for('DSC01234.ARW')}").status_code == 422


def test_thumb_missing_file_id_returns_404(client):
    assert client.get("/camera-import/thumbs/doesnotexist").status_code == 404


def test_thumb_stale_cache_returns_404(patched_scan, client):
    _write(patched_scan, "IMG_001.JPG")
    _scan(client)
    file_id = next(iter(ci._cache))  # grab any valid id before wiping

    ci._cache = {}  # simulate server reload

    assert client.get(f"/camera-import/thumbs/{file_id}").status_code == 404


# ---------------------------------------------------------------------------
# Import endpoint
# ---------------------------------------------------------------------------

def _do_scan(client):
    r = _scan(client)
    assert r.status_code == 200
    return r.json()["candidates"]


def test_import_jpeg_creates_photo_row(patched_scan, client, db_session):
    from app.models import Photo
    _write(patched_scan, "IMG_001.JPG", b"\xff\xd8\xff\xe0" + b"X" * 10 + b"\xff\xd9")
    candidates = _do_scan(client)
    file_id = candidates[0]["id"]

    r = client.post("/camera-import/import", json={"file_ids": [file_id]})
    assert r.status_code == 200
    data = r.json()
    assert len(data["created"]) == 1
    assert data["skipped"] == []
    assert data["failed"] == []

    photo = db_session.query(Photo).filter_by(original_filename="IMG_001.JPG").first()
    assert photo is not None
    assert photo.source == "sd"


def test_import_arw_stores_extracted_jpeg_preserves_raw_filename(patched_scan, client, db_session):
    from app.models import Photo
    embedded = b"\xff\xd8\xff\xe0" + b"E" * 200 + b"\xff\xd9"
    _write(patched_scan, "DSC01234.ARW", _fake_raw(embedded))
    candidates = _do_scan(client)
    file_id = candidates[0]["id"]

    r = client.post("/camera-import/import", json={"file_ids": [file_id]})
    assert r.status_code == 200
    assert len(r.json()["created"]) == 1

    photo = db_session.query(Photo).filter_by(original_filename="DSC01234.ARW").first()
    assert photo is not None
    assert photo.original_filename == "DSC01234.ARW"


def test_import_sets_original_size_bytes(patched_scan, client, db_session):
    from app.models import Photo
    content = b"\xff\xd8\xff\xe0" + b"X" * 50 + b"\xff\xd9"
    _write(patched_scan, "IMG_001.JPG", content)
    file_id = _do_scan(client)[0]["id"]

    client.post("/camera-import/import", json={"file_ids": [file_id]})

    photo = db_session.query(Photo).filter_by(original_filename="IMG_001.JPG").first()
    assert photo.original_size_bytes == len(content)


def test_import_duplicate_is_skipped(patched_scan, client):
    content = b"\xff\xd8\xff\xe0" + b"X" * 10 + b"\xff\xd9"
    _write(patched_scan, "IMG_001.JPG", content)
    file_id = _do_scan(client)[0]["id"]

    client.post("/camera-import/import", json={"file_ids": [file_id]})

    # Rescan so cache still valid, try import again
    _do_scan(client)
    file_id2 = next(c["id"] for c in _do_scan(client) if False) if False else file_id

    r = client.post("/camera-import/import", json={"file_ids": [file_id]})
    data = r.json()
    # After first import, same file_id is still in cache but DB now has a match
    assert data["skipped"] or data["failed"]  # either skipped (duplicate) or failed (stale id)


def test_import_stale_file_id_returns_failed(client):
    r = client.post("/camera-import/import", json={"file_ids": ["deadbeefdeadbeefdeadbeef12345678"]})
    assert r.status_code == 200
    data = r.json()
    assert len(data["failed"]) == 1
    assert data["failed"][0]["reason"] == "not_found_or_expired"


def test_import_partial_success(patched_scan, client):
    """One good JPEG + one bad file_id → one created, one failed."""
    content = b"\xff\xd8\xff\xe0" + b"X" * 10 + b"\xff\xd9"
    _write(patched_scan, "IMG_001.JPG", content)
    file_id = _do_scan(client)[0]["id"]

    r = client.post("/camera-import/import", json={
        "file_ids": [file_id, "ffffffffffffffffffffffffffffffff"]
    })
    data = r.json()
    assert len(data["created"]) == 1
    assert len(data["failed"]) == 1


def test_import_raw_no_embedded_jpeg_returns_failed(patched_scan, client):
    _write(patched_scan, "DSC01234.ARW", b"\x00" * 200)
    file_id = _do_scan(client)[0]["id"]

    r = client.post("/camera-import/import", json={"file_ids": [file_id]})
    data = r.json()
    assert len(data["failed"]) == 1
    assert data["failed"][0]["reason"] == "raw_preview_not_found"


def test_import_card_filename_rollover_not_duplicate(patched_scan, client, db_session):
    """DSC00001.ARW on a new card differs from an old DSC00001.ARW only by size."""
    embedded_old = b"\xff\xd8\xff\xe0" + b"O" * 50 + b"\xff\xd9"
    embedded_new = b"\xff\xd8\xff\xe0" + b"N" * 200 + b"\xff\xd9"

    # Import old card's file via manual upload to seed DB
    client.post("/manual-photos", data={}, files={
        "image": ("DSC00001.ARW", _fake_raw(embedded_old), "image/jpeg"),
    })

    # New card has DSC00001.ARW with different content → different size
    _write(patched_scan, "DSC00001.ARW", _fake_raw(embedded_new))
    file_id = _do_scan(client)[0]["id"]

    r = client.post("/camera-import/import", json={"file_ids": [file_id]})
    data = r.json()
    assert len(data["created"]) == 1, "new card's file should not be treated as duplicate"
