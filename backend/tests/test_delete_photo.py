from datetime import datetime, timezone

import pytest

from app.models import (
    Event, EventPhoto,
    GrowingUnit, Label,
    Photo, PhotoGrowingUnit, PhotoLabel, PhotoNote,
)


def _photo(db_session, isolated_photos_dir, stem="2026-05-26T100000Z", write_files=True):
    jpg  = isolated_photos_dir / f"{stem}.jpg"
    json = isolated_photos_dir / f"{stem}.json"
    if write_files:
        jpg.write_bytes(b"FAKEJPEG")
        json.write_bytes(b"{}")
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        storage_path=str(jpg),
        metadata_path=str(json),
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def test_delete_photo_returns_204(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    resp = client.delete(f"/photos/{photo.id}")
    assert resp.status_code == 204


def test_delete_photo_removes_db_row(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    client.delete(f"/photos/{photo.id}")
    assert db_session.query(Photo).filter_by(id=photo.id).first() is None


def test_delete_photo_removes_files(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    jpg  = isolated_photos_dir / f"2026-05-26T100000Z.jpg"
    json = isolated_photos_dir / f"2026-05-26T100000Z.json"
    assert jpg.exists() and json.exists()
    client.delete(f"/photos/{photo.id}")
    assert not jpg.exists()
    assert not json.exists()


def test_delete_photo_removes_notes(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    note = PhotoNote(photo_id=photo.id, note_text="hi", x=0.5, y=0.5)
    db_session.add(note)
    db_session.commit()
    client.delete(f"/photos/{photo.id}")
    assert db_session.query(PhotoNote).filter_by(photo_id=photo.id).count() == 0


def test_delete_photo_removes_labels(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    label = db_session.query(Label).first()
    db_session.add(PhotoLabel(photo_id=photo.id, label_id=label.id))
    db_session.commit()
    client.delete(f"/photos/{photo.id}")
    assert db_session.query(PhotoLabel).filter_by(photo_id=photo.id).count() == 0


def test_delete_photo_removes_growing_unit_links(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    unit = GrowingUnit(name="basil")
    db_session.add(unit)
    db_session.commit()
    db_session.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=unit.id))
    db_session.commit()
    client.delete(f"/photos/{photo.id}")
    assert db_session.query(PhotoGrowingUnit).filter_by(photo_id=photo.id).count() == 0


def test_delete_photo_removes_event_links(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir)
    ev = Event(event_type="watered", event_at=datetime(2026, 5, 26, tzinfo=timezone.utc))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventPhoto(event_id=ev.id, photo_id=photo.id))
    db_session.commit()
    client.delete(f"/photos/{photo.id}")
    assert db_session.query(EventPhoto).filter_by(photo_id=photo.id).count() == 0


def test_delete_photo_unknown_returns_404(client, db_session):
    resp = client.delete("/photos/99999")
    assert resp.status_code == 404


def test_delete_photo_tolerates_missing_files(client, db_session, isolated_photos_dir):
    photo = _photo(db_session, isolated_photos_dir, write_files=False)
    resp = client.delete(f"/photos/{photo.id}")
    assert resp.status_code == 204
    assert db_session.query(Photo).filter_by(id=photo.id).first() is None
