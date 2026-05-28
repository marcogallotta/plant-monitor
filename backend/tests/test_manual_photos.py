import json


def _upload(client, image_bytes=b"FAKEIMAGE", filename="IMG_001.jpg", **form_fields):
    return client.post("/manual-photos", data=form_fields, files={
        "image": (filename, image_bytes, "image/jpeg"),
    })


# --- POST /manual-photos basic ---

def test_manual_upload_returns_201(client):
    r = _upload(client)
    assert r.status_code == 201


def test_manual_upload_sets_source_manual(client):
    r = _upload(client)
    assert r.json()["source"] == "manual"


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


def test_manual_upload_invalid_rotation_returns_422(client):
    r = _upload(client, rotation=45)
    assert r.status_code == 422


def test_manual_upload_valid_rotations_accepted(client):
    for deg in (0, 90, 180, 270):
        r = _upload(client, rotation=deg)
        assert r.status_code == 201, f"rotation={deg} should be accepted"


# --- serve uploaded manual photo ---

def test_manual_upload_photo_is_servable(client, isolated_photos_dir):
    r = _upload(client, image_bytes=b"REALIMAGE")
    filename = r.json()["filename"]
    serve = client.get(f"/photos/{filename}")
    assert serve.status_code == 200
    assert serve.content == b"REALIMAGE"
