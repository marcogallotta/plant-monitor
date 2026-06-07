import json
from datetime import date, datetime, timezone
from io import BytesIO

from PIL import Image


def _upload(client, image_bytes=b"FAKEIMAGE", filename="IMG_001.jpg", **form_fields):
    return client.post("/manual-photos", data=form_fields, files={
        "image": (filename, image_bytes, "image/jpeg"),
    })


def _jpeg_with_exif(dto="2026:05:08 07:30:00", offset="+02:00"):
    img = Image.new("RGB", (8, 8), "green")
    buf = BytesIO()
    exif = Image.Exif()
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = dto  # DateTimeOriginal
    if offset is not None:
        ifd[0x9011] = offset  # OffsetTimeOriginal
    img.save(buf, "jpeg", exif=exif)
    return buf.getvalue()


# --- POST /manual-photos basic ---

def test_manual_upload_returns_201(client):
    r = _upload(client)
    assert r.status_code == 201


def test_manual_upload_sets_source_manual(client):
    r = _upload(client)
    assert r.json()["source"] == "manual"


def test_manual_upload_sets_source_phone(client):
    r = _upload(client, source="phone")
    assert r.json()["source"] == "phone"


def test_manual_upload_preserves_original_filename(client):
    r = _upload(client, filename="my_plant_photo.jpg")
    assert r.json()["original_filename"] == "my_plant_photo.jpg"


def test_manual_upload_stores_file(client, isolated_photos_dir):
    _upload(client)
    jpg_files = list(isolated_photos_dir.glob("*.jpg"))
    assert len(jpg_files) == 1


def test_manual_upload_creates_photo_row(client, db_session):
    from app.models import Photo
    _upload(client)
    assert db_session.query(Photo).count() == 1


def test_manual_upload_backend_filename_differs_from_original(client):
    r = _upload(client, filename="IMG_001.jpg")
    assert r.json()["filename"] != "IMG_001.jpg"


def test_manual_upload_response_has_url(client):
    r = _upload(client)
    data = r.json()
    assert data["url"].startswith("/photos/")


# --- optional fields ---

def test_manual_upload_accepts_captured_at(client):
    r = _upload(client, captured_at="2026-05-26T10:00:00Z")
    assert r.status_code == 201
    assert "2026-05-26" in r.json()["captured_at"]


def test_manual_upload_defaults_captured_at_to_now(client):
    r = _upload(client)
    assert r.status_code == 201
    assert r.json()["captured_at"] is not None


def test_manual_upload_accepts_photo_type(client):
    r = _upload(client, photo_type="closeup")
    assert r.json()["photo_type"] == "closeup"


def test_manual_upload_accepts_location(client):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    r = _upload(client, location_id=loc["id"])
    assert r.json()["location_id"] == loc["id"]


def test_manual_upload_bad_location_returns_404(client):
    r = _upload(client, location_id=99999)
    assert r.status_code == 404


def test_manual_upload_links_one_growing_unit(client):
    unit = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    r = client.post("/manual-photos", data={"growing_unit_ids": unit["id"]}, files={
        "image": ("IMG_001.jpg", b"FAKEIMAGE", "image/jpeg"),
    })
    assert r.status_code == 201
    assert any(u["id"] == unit["id"] for u in r.json()["growing_units"])


def test_manual_upload_links_multiple_growing_units(client):
    u1 = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    u2 = client.post("/growing-units", json={"name": "Genovese basil plant 1"}).json()
    r = client.post("/manual-photos", files=[
        ("image", ("IMG_001.jpg", b"FAKEIMAGE", "image/jpeg")),
        ("growing_unit_ids", (None, str(u1["id"]))),
        ("growing_unit_ids", (None, str(u2["id"]))),
    ])
    assert r.status_code == 201
    unit_ids = {u["id"] for u in r.json()["growing_units"]}
    assert unit_ids == {u1["id"], u2["id"]}


def test_manual_upload_bad_growing_unit_returns_404(client):
    r = client.post("/manual-photos", data={"growing_unit_ids": 99999}, files={
        "image": ("IMG_001.jpg", b"FAKEIMAGE", "image/jpeg"),
    })
    assert r.status_code == 404


def test_manual_upload_creates_initial_note(client, db_session):
    from app.models import PhotoNote
    r = _upload(client, note_text="First observation")
    assert r.status_code == 201
    photo_id = r.json()["id"]
    notes = db_session.query(PhotoNote).filter_by(photo_id=photo_id).all()
    assert len(notes) == 1
    assert notes[0].note_text == "First observation"


def test_manual_upload_no_note_text_creates_no_note(client, db_session):
    from app.models import PhotoNote
    r = _upload(client)
    photo_id = r.json()["id"]
    assert db_session.query(PhotoNote).filter_by(photo_id=photo_id).count() == 0


def test_manual_upload_non_jpeg_returns_415(client):
    r = client.post("/manual-photos", files={
        "image": ("photo.png", b"FAKEPNG", "image/png"),
    })
    assert r.status_code == 415


def test_manual_upload_bad_captured_at_returns_422(client):
    r = _upload(client, captured_at="not-a-date")
    assert r.status_code == 422


def test_manual_upload_uses_provided_original_size_bytes(client, db_session):
    from app.models import Photo
    r = client.post("/manual-photos", data={"original_size_bytes": 99999}, files={
        "image": ("DSC001.ARW", b"FAKEJPEG", "image/jpeg"),
    })
    assert r.status_code == 201
    photo = db_session.query(Photo).first()
    assert photo.original_size_bytes == 99999


def test_manual_upload_falls_back_to_image_size_without_original_size_bytes(client, db_session):
    from app.models import Photo
    image_bytes = b"FAKEJPEG"
    _upload(client, image_bytes=image_bytes)
    photo = db_session.query(Photo).first()
    assert photo.original_size_bytes == len(image_bytes)


def test_manual_upload_invalid_rotation_returns_422(client):
    r = _upload(client, rotation=45)
    assert r.status_code == 422


def test_manual_upload_valid_rotations_accepted(client):
    for deg in (0, 90, 180, 270):
        r = _upload(client, rotation=deg)
        assert r.status_code == 201, f"rotation={deg} should be accepted"


# --- EXIF capture-time authority ---

def test_exif_with_offset_overrides_client_captured_at(client):
    # Client sends a wrong captured_at (the lastModified-fallback bug); EXIF wins.
    r = _upload(
        client,
        image_bytes=_jpeg_with_exif("2026:05:08 07:30:00", "+02:00"),
        captured_at="2026-05-30T13:32:33Z",
    )
    assert r.status_code == 201
    # 07:30:00 +02:00 == 05:30:00 UTC
    assert r.json()["captured_at"].startswith("2026-05-08T05:30:00")


def test_exif_with_offset_used_when_no_captured_at(client):
    r = _upload(client, image_bytes=_jpeg_with_exif("2026:05:08 07:30:00", "+02:00"))
    assert r.status_code == 201
    assert r.json()["captured_at"].startswith("2026-05-08T05:30:00")


def test_exif_without_offset_does_not_override_client(client):
    # No UTC offset → ambiguous, so the client-supplied value is kept.
    r = _upload(
        client,
        image_bytes=_jpeg_with_exif("2026:05:08 07:30:00", offset=None),
        captured_at="2026-05-30T13:32:33Z",
    )
    assert r.status_code == 201
    assert r.json()["captured_at"].startswith("2026-05-30T13:32:33")


def test_no_exif_keeps_client_captured_at(client):
    r = _upload(client, image_bytes=b"FAKEIMAGE", captured_at="2026-05-30T13:32:33Z")
    assert r.status_code == 201
    assert r.json()["captured_at"].startswith("2026-05-30T13:32:33")


def test_exif_without_offset_and_no_captured_at_falls_back_to_now(client):
    # Old camera: DateTimeOriginal but no offset, and the client sends nothing.
    # We can't trust the ambiguous wall-clock time, so captured_at defaults to now.
    before = datetime.now(timezone.utc)
    r = _upload(client, image_bytes=_jpeg_with_exif("2026:05:08 07:30:00", offset=None))
    assert r.status_code == 201
    captured = datetime.fromisoformat(r.json()["captured_at"])
    # Not the (ambiguous) EXIF day, and within a sane window of upload time.
    assert captured.date() != date(2026, 5, 8)
    assert abs((captured - before).total_seconds()) < 120


# --- content-hash dedup ---

def test_identical_bytes_different_filename_dedups(client, db_session):
    from app.models import Photo
    img = b"IDENTICAL-BYTES-PAYLOAD"
    r1 = _upload(client, image_bytes=img, filename="1000116036.jpg")
    r2 = _upload(client, image_bytes=img, filename="image-1779889062712.jpg")
    assert r1.status_code == 201 and r2.status_code == 201
    # Same row returned both times; only one DB row and one file on disk.
    assert r1.json()["id"] == r2.json()["id"]
    assert db_session.query(Photo).count() == 1


def test_identical_bytes_writes_single_file(client, isolated_photos_dir):
    img = b"IDENTICAL-BYTES-PAYLOAD"
    _upload(client, image_bytes=img, filename="a.jpg")
    _upload(client, image_bytes=img, filename="b.jpg")
    assert len(list(isolated_photos_dir.glob("*.jpg"))) == 1


def test_different_bytes_are_not_deduped(client, db_session):
    from app.models import Photo
    _upload(client, image_bytes=b"PHOTO-ONE", filename="a.jpg")
    _upload(client, image_bytes=b"PHOTO-TWO", filename="b.jpg")
    assert db_session.query(Photo).count() == 2


def test_dedup_keeps_first_rows_metadata(client):
    # The duplicate upload does not overwrite the original's classification.
    img = b"IDENTICAL-BYTES-PAYLOAD"
    r1 = _upload(client, image_bytes=img, photo_type="health_check")
    r2 = _upload(client, image_bytes=img)  # no photo_type
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["photo_type"] == "health_check"


def test_dedup_is_first_upload_wins_for_all_fields(client):
    # Semantics: the first upload's location/rotation/captured_at survive; a
    # later byte-identical upload with different values does not change them.
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    img = b"IDENTICAL-BYTES-PAYLOAD-2"
    r1 = _upload(client, image_bytes=img, location_id=loc["id"], rotation=90,
                 captured_at="2026-05-08T05:30:00Z")
    r2 = _upload(client, image_bytes=img, rotation=270,
                 captured_at="2026-05-30T13:32:33Z")
    body = r2.json()
    assert body["id"] == r1.json()["id"]
    assert body["location_id"] == loc["id"]
    assert body["rotation"] == 90
    assert body["captured_at"].startswith("2026-05-08T05:30:00")


# --- serve uploaded manual photo ---

def test_manual_upload_photo_is_servable(client, isolated_photos_dir):
    r = _upload(client, image_bytes=b"REALIMAGE")
    filename = r.json()["filename"]
    serve = client.get(f"/photos/{filename}")
    assert serve.status_code == 200
    assert serve.content == b"REALIMAGE"
