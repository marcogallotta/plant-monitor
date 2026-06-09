import io
from datetime import datetime, timezone

import pytest
from PIL import Image

import app.main
import app.helpers
from app.models import Photo

_CAPTURED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)


def _photo(db, stem="2026-05-26T100000Z", rotation=0):
    photos_dir = app.main.PHOTOS_DIR
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=_CAPTURED_AT,
        storage_path=str(photos_dir / f"{stem}.jpg"),
        metadata_path=str(photos_dir / f"{stem}.json"),
        rotation=rotation,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _write_jpeg(photos_dir, stem, width=120, height=80):
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    (photos_dir / f"{stem}.jpg").write_bytes(buf.getvalue())


@pytest.fixture(autouse=True)
def isolated_thumbs_dir(tmp_path, monkeypatch):
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    monkeypatch.setattr("app.helpers.THUMBS_DIR", thumbs)
    monkeypatch.setattr("app.main.THUMBS_DIR", thumbs)
    return thumbs


# --- basic ---

def test_thumbnail_returns_jpeg(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)

    resp = client.get(f"/photos/{stem}.jpg/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_thumbnail_missing_photo_returns_404(client):
    resp = client.get("/photos/2026-05-26T100000Z.jpg/thumbnail")
    assert resp.status_code == 404


def test_thumbnail_invalid_filename_returns_422(client):
    resp = client.get("/photos/invalid!name.jpg/thumbnail")
    assert resp.status_code == 422


# --- size ---

def test_thumbnail_respects_size(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem, width=200, height=200)

    resp = client.get(f"/photos/{stem}.jpg/thumbnail?size=50")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.content))
    assert max(img.size) <= 50


def test_thumbnail_size_boundary_min(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)
    assert client.get(f"/photos/{stem}.jpg/thumbnail?size=1").status_code == 200


def test_thumbnail_size_boundary_max(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)
    assert client.get(f"/photos/{stem}.jpg/thumbnail?size=1600").status_code == 200


def test_thumbnail_size_out_of_range_returns_422(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)
    assert client.get(f"/photos/{stem}.jpg/thumbnail?size=1601").status_code == 422


# --- oriented ---

def test_thumbnail_oriented_bakes_rotation(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem, rotation=90)
    _write_jpeg(isolated_photos_dir, stem, width=120, height=80)

    resp = client.get(f"/photos/{stem}.jpg/thumbnail?oriented=true&size=400")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.content))
    # 120×80 rotated 90° → portrait (height > width)
    assert img.height > img.width


def test_thumbnail_unoriented_preserves_dimensions(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem, rotation=90)
    _write_jpeg(isolated_photos_dir, stem, width=120, height=80)

    resp = client.get(f"/photos/{stem}.jpg/thumbnail?oriented=false&size=400")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.content))
    assert img.width > img.height


# --- cache ---

def test_thumbnail_cache_hit_returns_same_content(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)

    url = f"/photos/{stem}.jpg/thumbnail"
    first = client.get(url).content
    second = client.get(url).content
    assert first == second


def test_thumbnail_cache_is_written(client, db_session, isolated_photos_dir, isolated_thumbs_dir):
    stem = "2026-05-26T100000Z"
    _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)

    client.get(f"/photos/{stem}.jpg/thumbnail?size=400")
    cached = list(isolated_thumbs_dir.rglob("*.jpg"))
    assert len(cached) == 1
