import io
import zipfile
from datetime import datetime, timezone

import pytest
from PIL import Image

import app.main
from app.models import Photo

_CAPTURED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)


def _photo(db, stem, rotation=0):
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


def _write_jpeg(photos_dir, stem):
    img = Image.new("RGB", (100, 80), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    (photos_dir / f"{stem}.jpg").write_bytes(buf.getvalue())


# --- validation ---

def test_export_non_numeric_id_returns_422(client):
    assert client.get("/photos/export?ids=abc").status_code == 422


def test_export_empty_ids_returns_422(client):
    assert client.get("/photos/export?ids=").status_code == 422


def test_export_unknown_ids_returns_404(client):
    assert client.get("/photos/export?ids=9999").status_code == 404


# --- happy path ---

def test_export_returns_zip(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    photo = _photo(db_session, stem)
    _write_jpeg(isolated_photos_dir, stem)

    resp = client.get(f"/photos/export?ids={photo.id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "photos.zip" in resp.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert f"{stem}.jpg" in zf.namelist()


def test_export_multiple_photos(client, db_session, isolated_photos_dir):
    stems = ["2026-05-26T100000Z", "2026-05-26T110000Z"]
    ids = []
    for stem in stems:
        p = _photo(db_session, stem)
        _write_jpeg(isolated_photos_dir, stem)
        ids.append(p.id)

    resp = client.get(f"/photos/export?ids={','.join(str(i) for i in ids)}")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert set(zf.namelist()) == {f"{s}.jpg" for s in stems}


def test_export_missing_file_silently_skipped(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    photo = _photo(db_session, stem)
    # no file written to disk

    resp = client.get(f"/photos/export?ids={photo.id}")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert zf.namelist() == []


def test_export_rotated_photo_bakes_rotation(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    photo = _photo(db_session, stem, rotation=90)
    _write_jpeg(isolated_photos_dir, stem)

    resp = client.get(f"/photos/export?ids={photo.id}")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    # image is re-encoded JPEG — verify it's readable and dimensions are swapped
    img = Image.open(io.BytesIO(zf.read(f"{stem}.jpg")))
    assert img.size == (80, 100)  # 100×80 rotated 90° → 80×100
