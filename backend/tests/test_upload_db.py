import json
import pytest
from fastapi.testclient import TestClient

from app.models import Photo

STEM_1 = "2026-05-26T120000Z"
STEM_2 = "2026-05-26T130000Z"
STEM_3 = "2026-05-26T140000Z"


def _upload(client, stem, image_bytes=b"FAKEJPEG", captured_at="2026-05-26T12:00:00Z"):
    meta = {"captured_at": captured_at, "filename": f"{stem}.jpg"}
    return client.post(
        "/photos",
        files={
            "image": (f"{stem}.jpg", image_bytes, "image/jpeg"),
            "metadata": (f"{stem}.json", json.dumps(meta).encode(), "application/json"),
        },
    )


def test_upload_creates_photo_record(client, db_session):
    _upload(client, STEM_1)
    photo = db_session.query(Photo).filter_by(filename=f"{STEM_1}.jpg").one()
    assert photo.filename == f"{STEM_1}.jpg"


def test_upload_photo_record_fields(client, db_session):
    _upload(client, STEM_2, captured_at="2026-05-26T13:00:00Z")
    photo = db_session.query(Photo).filter_by(filename=f"{STEM_2}.jpg").one()
    assert photo.captured_at.isoformat().startswith("2026-05-26T13:00:00")
    assert f"{STEM_2}.jpg" in photo.storage_path
    assert f"{STEM_2}.json" in photo.metadata_path


def test_duplicate_upload_does_not_create_second_record(client, db_session):
    _upload(client, STEM_3)
    _upload(client, STEM_3)
    count = db_session.query(Photo).filter_by(filename=f"{STEM_3}.jpg").count()
    assert count == 1
