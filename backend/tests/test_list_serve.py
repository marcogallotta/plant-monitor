from datetime import datetime
from app.models import Photo


def _photo(db_session, stem, captured_at_str):
    captured_at = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=f"data/photos/{stem}.jpg",
        metadata_path=f"data/photos/{stem}.json",
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
    assert client.get("/photos/notadate.jpg").status_code == 422


def test_serve_photo_path_traversal_does_not_serve_file(client):
    # URL normalisation collapses ../../ before the request reaches the route handler,
    # so the response is 404 (no matching route), not 422. Either way the file is not served.
    assert client.get("/photos/../../etc/passwd.jpg").status_code != 200
