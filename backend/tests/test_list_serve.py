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


# --- GET /photos/{filename}?oriented=1 ---

import io
from PIL import Image


def _write_split_jpeg(path, w=16, h=8, top=(255, 0, 0), bottom=(0, 0, 255)):
    """Landscape JPEG, top half red, bottom half blue — asymmetric so rotation
    direction is observable."""
    im = Image.new("RGB", (w, h))
    for y in range(h):
        for x in range(w):
            im.putpixel((x, y), top if y < h // 2 else bottom)
    im.save(path, format="JPEG", quality=95)


def _rotated_photo(db_session, stem, rotation):
    photo = _photo(db_session, stem, "2026-05-26T10:00:00Z")
    photo.rotation = rotation
    db_session.commit()
    return photo


def _is_reddish(px):
    return px[0] > 150 and px[2] < 100


def _is_bluish(px):
    return px[2] > 150 and px[0] < 100


def test_serve_oriented_rotates_90_clockwise(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _write_split_jpeg(isolated_photos_dir / f"{stem}.jpg")
    _rotated_photo(db_session, stem, 90)
    resp = client.get(f"/photos/{stem}.jpg?oriented=1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    out = Image.open(io.BytesIO(resp.content))
    assert out.size == (8, 16)  # dimensions swapped
    # CSS rotate(90deg) is clockwise: the original top (red) ends up on the right.
    assert _is_reddish(out.getpixel((7, 8)))
    assert _is_bluish(out.getpixel((0, 8)))


def test_serve_oriented_rotates_180(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _write_split_jpeg(isolated_photos_dir / f"{stem}.jpg")
    _rotated_photo(db_session, stem, 180)
    out = Image.open(io.BytesIO(client.get(f"/photos/{stem}.jpg?oriented=1").content))
    assert out.size == (16, 8)  # unchanged
    # top half was red, now blue (flipped vertically + horizontally)
    assert _is_bluish(out.getpixel((8, 2)))
    assert _is_reddish(out.getpixel((8, 6)))


def test_serve_oriented_rotates_270(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _write_split_jpeg(isolated_photos_dir / f"{stem}.jpg")
    _rotated_photo(db_session, stem, 270)
    out = Image.open(io.BytesIO(client.get(f"/photos/{stem}.jpg?oriented=1").content))
    assert out.size == (8, 16)  # swapped
    # 270 CW: original top (red) ends up on the left
    assert _is_reddish(out.getpixel((0, 8)))
    assert _is_bluish(out.getpixel((7, 8)))


def test_serve_oriented_rotation_zero_returns_original_bytes(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _write_split_jpeg(isolated_photos_dir / f"{stem}.jpg")
    _rotated_photo(db_session, stem, 0)
    original = (isolated_photos_dir / f"{stem}.jpg").read_bytes()
    resp = client.get(f"/photos/{stem}.jpg?oriented=1")
    assert resp.status_code == 200
    assert resp.content == original  # untouched, no re-encode


def test_serve_oriented_leaves_original_file_untouched(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    path = isolated_photos_dir / f"{stem}.jpg"
    _write_split_jpeg(path)
    _rotated_photo(db_session, stem, 90)
    before = path.read_bytes()
    client.get(f"/photos/{stem}.jpg?oriented=1")
    assert path.read_bytes() == before


def test_serve_without_oriented_returns_raw_unrotated(client, db_session, isolated_photos_dir):
    """Regression: the plain serve endpoint never rotates, even for a rotated photo."""
    stem = "2026-05-26T100000Z"
    path = isolated_photos_dir / f"{stem}.jpg"
    _write_split_jpeg(path)
    _rotated_photo(db_session, stem, 90)
    resp = client.get(f"/photos/{stem}.jpg")
    assert resp.status_code == 200
    assert resp.content == path.read_bytes()


def test_serve_oriented_invalid_filename_still_422(client):
    assert client.get("/photos/not_valid!.jpg?oriented=1").status_code == 422


def test_serve_oriented_corrupt_image_returns_422(client, db_session, isolated_photos_dir):
    """A file that Pillow can't decode must surface as a 422, not a 500."""
    stem = "2026-05-26T100000Z"
    (isolated_photos_dir / f"{stem}.jpg").write_bytes(b"this is not a jpeg")
    _rotated_photo(db_session, stem, 90)
    assert client.get(f"/photos/{stem}.jpg?oriented=1").status_code == 422
