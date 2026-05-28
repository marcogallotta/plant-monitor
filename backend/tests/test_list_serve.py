from datetime import datetime, timezone
import app.main
from app.models import Photo


def _photo(db_session, stem, captured_at_str):
    captured_at = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
    photos_dir = app.main.PHOTOS_DIR
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(photos_dir / f"{stem}.jpg"),
        metadata_path=str(photos_dir / f"{stem}.json"),
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


# --- GET /photos ---

def test_list_photos_empty(client):
    assert client.get("/photos").json() == []


def test_list_photos_returns_photo(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    data = client.get("/photos").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T100000Z.jpg"
    assert data[0]["url"] == "/photos/2026-05-26T100000Z.jpg"
    assert "id" in data[0]
    assert "captured_at" in data[0]


def test_list_photos_sorted_by_captured_at(client, db_session):
    _photo(db_session, "2026-05-26T120000Z", "2026-05-26T12:00:00Z")
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    data = client.get("/photos").json()
    filenames = [d["filename"] for d in data]
    assert filenames == [
        "2026-05-26T100000Z.jpg",
        "2026-05-26T110000Z.jpg",
        "2026-05-26T120000Z.jpg",
    ]


def test_list_photos_filter_start(client, db_session):
    _photo(db_session, "2026-05-26T090000Z", "2026-05-26T09:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    data = client.get("/photos?start=2026-05-26T10:00:00Z").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T110000Z.jpg"


def test_list_photos_filter_end(client, db_session):
    _photo(db_session, "2026-05-26T090000Z", "2026-05-26T09:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    data = client.get("/photos?end=2026-05-26T10:00:00Z").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T090000Z.jpg"


def test_list_photos_filter_range(client, db_session):
    _photo(db_session, "2026-05-26T080000Z", "2026-05-26T08:00:00Z")
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T120000Z", "2026-05-26T12:00:00Z")
    data = client.get("/photos?start=2026-05-26T09:00:00Z&end=2026-05-26T11:00:00Z").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T100000Z.jpg"


# --- GET /photos/{filename} ---

def test_serve_photo_returns_file_content(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    (isolated_photos_dir / f"{stem}.jpg").write_bytes(b"IMAGEDATA")
    _photo(db_session, stem, "2026-05-26T10:00:00Z")
    resp = client.get(f"/photos/{stem}.jpg")
    assert resp.status_code == 200
    assert resp.content == b"IMAGEDATA"


def test_serve_photo_not_in_db_returns_404(client, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    (isolated_photos_dir / f"{stem}.jpg").write_bytes(b"IMAGEDATA")
    assert client.get(f"/photos/{stem}.jpg").status_code == 404


def test_serve_photo_invalid_extension_returns_422(client):
    assert client.get("/photos/2026-05-26T100000Z.png").status_code == 422


def test_serve_photo_invalid_stem_returns_422(client):
    # contains '!' which fails the safe filename regex
    assert client.get("/photos/not_valid!.jpg").status_code == 422


def test_serve_photo_path_traversal_does_not_serve_file(client):
    # URL normalisation collapses ../../ before the request reaches the route handler,
    # so the response is 404 (no matching route), not 422. Either way the file is not served.
    assert client.get("/photos/../../etc/passwd.jpg").status_code != 200


_NOW = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)


def test_serve_photo_storage_path_outside_photos_dir_returns_404(client, db_session):
    """DB row whose storage_path points outside PHOTOS_DIR is rejected by the path check."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as outside_dir:
        outside = Path(outside_dir) / "2026-05-26T100000Z.jpg"
        outside.write_bytes(b"SECRET")
        photo = Photo(
            filename="2026-05-26T100000Z.jpg",
            captured_at=_NOW,
            storage_path=str(outside),
            metadata_path="",
        )
        db_session.add(photo)
        db_session.commit()
        assert client.get("/photos/2026-05-26T100000Z.jpg").status_code == 404


def test_serve_photo_file_not_on_disk_returns_404(client, db_session, isolated_photos_dir):
    """DB row exists but the file was deleted from disk → 404."""
    stem = "2026-05-26T100000Z"
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=_NOW,
        storage_path=str(isolated_photos_dir / f"{stem}.jpg"),
        metadata_path="",
    )
    db_session.add(photo)
    db_session.commit()
    # file is deliberately not written to disk
    assert client.get(f"/photos/{stem}.jpg").status_code == 404
