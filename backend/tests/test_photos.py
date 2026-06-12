import json
import pytest

VALID_STEM = "2026-05-26T103000Z"
VALID_META = {"captured_at": "2026-05-26T10:30:00Z", "filename": f"{VALID_STEM}.jpg"}


def _upload(client, stem=VALID_STEM, image_bytes=b"FAKEJPEG", meta=None):
    if meta is None:
        meta = {"captured_at": "2026-05-26T10:30:00Z", "filename": f"{stem}.jpg"}
    return client.post(
        "/photos",
        files={
            "image": (f"{stem}.jpg", image_bytes, "image/jpeg"),
            "metadata": (
                f"{stem}.json",
                json.dumps(meta).encode(),
                "application/json",
            ),
        },
    )


# --- happy path ---

def test_upload_returns_200(client):
    assert _upload(client).status_code == 200


def test_upload_writes_image(client, isolated_photos_dir):
    _upload(client, image_bytes=b"IMGDATA")
    assert (isolated_photos_dir / f"{VALID_STEM}.jpg").read_bytes() == b"IMGDATA"


def test_upload_writes_metadata(client, isolated_photos_dir):
    _upload(client)
    meta = json.loads((isolated_photos_dir / f"{VALID_STEM}.json").read_text())
    assert meta["captured_at"] == "2026-05-26T10:30:00Z"
    assert meta["filename"] == f"{VALID_STEM}.jpg"


def test_both_files_exist_after_response(client, isolated_photos_dir):
    _upload(client)
    assert (isolated_photos_dir / f"{VALID_STEM}.jpg").exists()
    assert (isolated_photos_dir / f"{VALID_STEM}.json").exists()


def test_upload_removes_files_when_db_write_fails(client, isolated_photos_dir, monkeypatch):
    def fail_upsert(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.main._upsert_photo_record", fail_upsert)

    with pytest.raises(RuntimeError, match="database unavailable"):
        _upload(client)

    assert not (isolated_photos_dir / f"{VALID_STEM}.jpg").exists()
    assert not (isolated_photos_dir / f"{VALID_STEM}.json").exists()


# --- duplicate ---

def test_full_duplicate_returns_200(client):
    _upload(client)
    assert _upload(client).status_code == 200


def test_full_duplicate_does_not_overwrite_image(client, isolated_photos_dir):
    _upload(client, image_bytes=b"FIRST")
    _upload(client, image_bytes=b"SECOND")
    assert (isolated_photos_dir / f"{VALID_STEM}.jpg").read_bytes() == b"FIRST"


# --- partial duplicate → 409 ---

def test_image_exists_without_metadata_returns_409(client, isolated_photos_dir):
    (isolated_photos_dir / f"{VALID_STEM}.jpg").write_bytes(b"ORPHAN")
    assert _upload(client).status_code == 409


def test_metadata_exists_without_image_returns_409(client, isolated_photos_dir):
    (isolated_photos_dir / f"{VALID_STEM}.json").write_text(json.dumps(VALID_META))
    assert _upload(client).status_code == 409


# --- filename validation ---

def test_wrong_image_extension_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": (f"{VALID_STEM}.png", b"X", "image/png"),
            "metadata": (f"{VALID_STEM}.json", b"{}", "application/json"),
        },
    )
    assert response.status_code == 422


def test_wrong_metadata_extension_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": (f"{VALID_STEM}.jpg", b"X", "image/jpeg"),
            "metadata": (f"{VALID_STEM}.txt", b"{}", "text/plain"),
        },
    )
    assert response.status_code == 422


def test_invalid_stem_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": ("../../etc/passwd.jpg", b"X", "image/jpeg"),
            "metadata": ("../../etc/passwd.json", b"{}", "application/json"),
        },
    )
    assert response.status_code == 422


def test_stem_without_timestamp_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": ("photo.jpg", b"X", "image/jpeg"),
            "metadata": ("photo.json", b"{}", "application/json"),
        },
    )
    assert response.status_code == 422


def test_mismatched_stems_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": (f"{VALID_STEM}.jpg", b"X", "image/jpeg"),
            "metadata": ("2026-05-26T110000Z.json", b"{}", "application/json"),
        },
    )
    assert response.status_code == 422


# --- metadata validation ---

def test_missing_captured_at_returns_422(client):
    assert _upload(client, meta={"filename": f"{VALID_STEM}.jpg"}).status_code == 422


def test_missing_filename_returns_422(client):
    assert _upload(client, meta={"captured_at": "2026-05-26T10:30:00Z"}).status_code == 422


def test_metadata_filename_mismatch_returns_422(client):
    meta = {"captured_at": "2026-05-26T10:30:00Z", "filename": "2026-05-26T110000Z.jpg"}
    assert _upload(client, meta=meta).status_code == 422


def test_invalid_captured_at_returns_422(client):
    assert _upload(client, meta={"captured_at": "not-a-date", "filename": f"{VALID_STEM}.jpg"}).status_code == 422


def test_valid_image_stem_invalid_metadata_stem_returns_422(client):
    """Image stem is a valid timestamp; metadata stem is not → 422 on metadata stem check."""
    response = client.post(
        "/photos",
        files={
            "image": (f"{VALID_STEM}.jpg", b"X", "image/jpeg"),
            "metadata": ("photo.json", b"{}", "application/json"),
        },
    )
    assert response.status_code == 422


def test_non_json_metadata_returns_422(client):
    response = client.post(
        "/photos",
        files={
            "image": (f"{VALID_STEM}.jpg", b"X", "image/jpeg"),
            "metadata": (f"{VALID_STEM}.json", b"not valid json {{{{", "application/json"),
        },
    )
    assert response.status_code == 422
