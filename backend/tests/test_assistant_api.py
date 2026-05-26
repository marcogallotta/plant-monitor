import io
from datetime import datetime, timezone

import pytest
from PIL import Image

import app.main
from app.models import (
    Event, EventGrowingUnit, EventPhoto,
    GrowingUnit, Location, Photo, PhotoGrowingUnit, PhotoNote,
)


def _location(db, name="Location A"):
    loc = Location(name=name)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def _growing_unit(db, name="Unit A", location_id=None):
    unit = GrowingUnit(name=name, current_location_id=location_id)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def _photo(db, stem="2026-05-26T100000Z", photo_type=None, location_id=None):
    photos_dir = app.main.PHOTOS_DIR
    date_part, time_part = stem.split("T")
    t = time_part.rstrip("Z")
    captured_at = datetime.fromisoformat(f"{date_part}T{t[:2]}:{t[2:4]}:{t[4:6]}+00:00")
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(photos_dir / f"{stem}.jpg"),
        metadata_path=str(photos_dir / f"{stem}.json"),
        photo_type=photo_type,
        location_id=location_id,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _event(db, event_type="watering", location_id=None):
    ev = Event(
        event_type=event_type,
        event_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        location_id=location_id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _jpeg(photos_dir, stem):
    img = Image.new("RGB", (1000, 800), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    (photos_dir / f"{stem}.jpg").write_bytes(buf.getvalue())


# --- GET /assistant/summary ---

def test_summary_empty(client):
    data = client.get("/assistant/summary").json()
    assert data["photo_count"] == 0
    assert data["unclassified_count"] == 0
    assert data["growing_unit_count"] == 0
    assert data["location_count"] == 0
    assert data["event_count"] == 0
    assert data["recent_photos"] == []


def test_summary_counts(client, db_session):
    _location(db_session)
    _growing_unit(db_session)
    _photo(db_session, photo_type="overview")
    _photo(db_session, stem="2026-05-26T110000Z")
    _event(db_session)
    data = client.get("/assistant/summary").json()
    assert data["photo_count"] == 2
    assert data["unclassified_count"] == 1
    assert data["growing_unit_count"] == 1
    assert data["location_count"] == 1
    assert data["event_count"] == 1


def test_summary_recent_photos_capped_at_five(client, db_session):
    for h in range(10, 17):
        _photo(db_session, stem=f"2026-05-26T{h:02d}0000Z")
    data = client.get("/assistant/summary").json()
    assert len(data["recent_photos"]) == 5


# --- GET /assistant/photos ---

def test_assistant_photos_empty(client):
    assert client.get("/assistant/photos").json() == []


def test_assistant_photos_returns_photos(client, db_session):
    _photo(db_session)
    data = client.get("/assistant/photos").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T100000Z.jpg"


def test_assistant_photos_filter_start(client, db_session):
    _photo(db_session, "2026-05-26T090000Z")
    _photo(db_session, "2026-05-26T110000Z")
    data = client.get("/assistant/photos?start=2026-05-26T10:00:00Z").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T110000Z.jpg"


def test_assistant_photos_filter_source(client, db_session):
    photo = _photo(db_session)
    photo.source = "pi"
    db_session.commit()
    _photo(db_session, stem="2026-05-26T110000Z")
    data = client.get("/assistant/photos?source=pi").json()
    assert len(data) == 1


def test_assistant_photos_includes_growing_units(client, db_session):
    unit = _growing_unit(db_session)
    photo = _photo(db_session)
    db_session.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=unit.id))
    db_session.commit()
    data = client.get("/assistant/photos").json()
    assert len(data[0]["growing_units"]) == 1
    assert data[0]["growing_units"][0]["name"] == "Unit A"


# --- GET /assistant/photos/{photo_id} ---

def test_assistant_get_photo(client, db_session):
    photo = _photo(db_session)
    data = client.get(f"/assistant/photos/{photo.id}").json()
    assert data["id"] == photo.id
    assert data["filename"] == "2026-05-26T100000Z.jpg"


def test_assistant_get_photo_not_found(client):
    assert client.get("/assistant/photos/99999").status_code == 404


# --- GET /assistant/photos/{photo_id}/context ---

def test_assistant_photo_context_fields(client, db_session):
    photo = _photo(db_session)
    data = client.get(f"/assistant/photos/{photo.id}/context").json()
    assert "photo" in data
    assert "notes" in data
    assert "events" in data


def test_assistant_photo_context_includes_notes(client, db_session):
    photo = _photo(db_session)
    db_session.add(PhotoNote(photo_id=photo.id, note_text="yellowing", x=0.5, y=0.5))
    db_session.commit()
    data = client.get(f"/assistant/photos/{photo.id}/context").json()
    assert len(data["notes"]) == 1
    assert data["notes"][0]["note_text"] == "yellowing"


def test_assistant_photo_context_includes_linked_events(client, db_session):
    photo = _photo(db_session)
    ev = _event(db_session)
    db_session.add(EventPhoto(event_id=ev.id, photo_id=photo.id))
    db_session.commit()
    data = client.get(f"/assistant/photos/{photo.id}/context").json()
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "watering"


def test_assistant_photo_context_not_found(client):
    assert client.get("/assistant/photos/99999/context").status_code == 404


# --- GET /assistant/photos/{photo_id}/thumbnail ---

def test_assistant_photo_thumbnail(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    _jpeg(isolated_photos_dir, stem)
    photo = _photo(db_session, stem)
    resp = client.get(f"/assistant/photos/{photo.id}/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    thumb = Image.open(io.BytesIO(resp.content))
    assert max(thumb.size) <= 256


def test_assistant_photo_thumbnail_not_found(client):
    assert client.get("/assistant/photos/99999/thumbnail").status_code == 404


def test_assistant_photo_thumbnail_file_missing(client, db_session):
    photo = _photo(db_session)
    assert client.get(f"/assistant/photos/{photo.id}/thumbnail").status_code == 404


def test_assistant_photo_thumbnail_corrupt_file_returns_422(client, db_session, isolated_photos_dir):
    stem = "2026-05-26T100000Z"
    (isolated_photos_dir / f"{stem}.jpg").write_bytes(b"not a jpeg")
    photo = _photo(db_session, stem)
    assert client.get(f"/assistant/photos/{photo.id}/thumbnail").status_code == 422


def test_assistant_photo_thumbnail_path_traversal_blocked(client, db_session):
    import tempfile
    from pathlib import Path as _Path
    with tempfile.TemporaryDirectory() as tmpdir:
        outside = _Path(tmpdir) / "outside.jpg"
        img = Image.new("RGB", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        outside.write_bytes(buf.getvalue())

        photo = Photo(
            filename="legit.jpg",
            captured_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
            storage_path=str(outside),
            metadata_path="",
        )
        db_session.add(photo)
        db_session.commit()
        db_session.refresh(photo)

        assert client.get(f"/assistant/photos/{photo.id}/thumbnail").status_code == 404


# --- GET /assistant/growing-units ---

def test_assistant_growing_units_empty(client):
    assert client.get("/assistant/growing-units").json() == []


def test_assistant_growing_units_returns_units(client, db_session):
    _growing_unit(db_session)
    data = client.get("/assistant/growing-units").json()
    assert len(data) == 1
    assert data[0]["name"] == "Unit A"


# --- GET /assistant/growing-units/{id}/context ---

def test_assistant_growing_unit_context_fields(client, db_session):
    unit = _growing_unit(db_session)
    data = client.get(f"/assistant/growing-units/{unit.id}/context").json()
    assert "growing_unit" in data
    assert "photos" in data
    assert "events" in data


def test_assistant_growing_unit_context_includes_photos(client, db_session):
    unit = _growing_unit(db_session)
    photo = _photo(db_session)
    db_session.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=unit.id))
    db_session.commit()
    data = client.get(f"/assistant/growing-units/{unit.id}/context").json()
    assert len(data["photos"]) == 1


def test_assistant_growing_unit_context_includes_events(client, db_session):
    unit = _growing_unit(db_session)
    ev = _event(db_session)
    db_session.add(EventGrowingUnit(event_id=ev.id, growing_unit_id=unit.id))
    db_session.commit()
    data = client.get(f"/assistant/growing-units/{unit.id}/context").json()
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "watering"


def test_assistant_growing_unit_context_not_found(client):
    assert client.get("/assistant/growing-units/99999/context").status_code == 404


# --- GET /assistant/locations ---

def test_assistant_locations_empty(client):
    assert client.get("/assistant/locations").json() == []


def test_assistant_locations_returns_locations(client, db_session):
    _location(db_session)
    data = client.get("/assistant/locations").json()
    assert len(data) == 1
    assert data[0]["name"] == "Location A"


# --- GET /assistant/events ---

def test_assistant_events_empty(client):
    assert client.get("/assistant/events").json() == []


def test_assistant_events_returns_events(client, db_session):
    _event(db_session)
    data = client.get("/assistant/events").json()
    assert len(data) == 1
    assert data[0]["event_type"] == "watering"


# --- GET /assistant/unclassified ---

def test_assistant_unclassified_empty_when_all_classified(client, db_session):
    _photo(db_session, photo_type="overview")
    assert client.get("/assistant/unclassified").json() == []


def test_assistant_unclassified_returns_photos_without_type(client, db_session):
    _photo(db_session, photo_type="overview")
    _photo(db_session, stem="2026-05-26T110000Z")
    data = client.get("/assistant/unclassified").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T110000Z.jpg"


def test_assistant_unclassified_empty(client):
    assert client.get("/assistant/unclassified").json() == []
