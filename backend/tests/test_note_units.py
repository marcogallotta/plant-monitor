"""Region tagging: a PhotoNote can carry a growing_unit_id (tag a unit on a
specific frame), and a note may be a pure unit-tag with no prose."""
from datetime import datetime, timezone

from app.models import Photo, GrowingUnit


def _photo(db_session, stem="2026-05-26T100000Z"):
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        storage_path=f"data/photos/{stem}.jpg",
        metadata_path=f"data/photos/{stem}.json",
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def _unit(db_session, name="Lemongrass"):
    u = GrowingUnit(name=name)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_create_region_note_with_unit(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={
        "x": 0.1, "y": 0.2, "x2": 0.3, "y2": 0.4, "growing_unit_id": unit.id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["growing_unit_id"] == unit.id
    assert body["note_text"] is None


def test_create_unit_note_without_text_allowed(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={
        "x": 0.5, "y": 0.5, "growing_unit_id": unit.id})
    assert resp.status_code == 201


def test_create_text_only_note_still_works(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={
        "note_text": "hi", "x": 0.5, "y": 0.5})
    assert resp.status_code == 201
    assert resp.json()["growing_unit_id"] is None


def test_create_note_requires_text_or_unit(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={"x": 0.5, "y": 0.5})
    assert resp.status_code == 422


def test_create_note_unknown_unit_returns_404(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={
        "x": 0.5, "y": 0.5, "growing_unit_id": 99999})
    assert resp.status_code == 404


def test_list_notes_includes_unit(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    client.post(f"/photos/{photo.id}/notes", json={
        "x": 0.1, "y": 0.2, "growing_unit_id": unit.id})
    resp = client.get(f"/photos/{photo.id}/notes")
    assert resp.status_code == 200
    assert resp.json()[0]["growing_unit_id"] == unit.id


def test_update_note_set_unit(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    note = client.post(f"/photos/{photo.id}/notes", json={
        "note_text": "x", "x": 0.5, "y": 0.5}).json()
    resp = client.put(f"/notes/{note['id']}", json={"growing_unit_id": unit.id})
    assert resp.status_code == 200
    assert resp.json()["growing_unit_id"] == unit.id


def test_update_note_clear_unit(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    note = client.post(f"/photos/{photo.id}/notes", json={
        "note_text": "x", "x": 0.5, "y": 0.5, "growing_unit_id": unit.id}).json()
    resp = client.put(f"/notes/{note['id']}", json={"growing_unit_id": None})
    assert resp.status_code == 200
    assert resp.json()["growing_unit_id"] is None
    assert resp.json()["note_text"] == "x"


def test_update_note_unknown_unit_returns_404(client, db_session):
    photo, unit = _photo(db_session), _unit(db_session)
    note = client.post(f"/photos/{photo.id}/notes", json={
        "note_text": "x", "x": 0.5, "y": 0.5}).json()
    resp = client.put(f"/notes/{note['id']}", json={"growing_unit_id": 99999})
    assert resp.status_code == 404


def test_update_note_clearing_last_unit_rejected(client, db_session):
    """A unit-only note (no text) cannot have its unit cleared — that would
    leave an empty note with neither text nor unit."""
    photo, unit = _photo(db_session), _unit(db_session)
    note = client.post(f"/photos/{photo.id}/notes", json={
        "x": 0.5, "y": 0.5, "growing_unit_id": unit.id}).json()
    resp = client.put(f"/notes/{note['id']}", json={"growing_unit_id": None})
    assert resp.status_code == 422
    # the note is unchanged
    listed = client.get(f"/photos/{photo.id}/notes").json()
    assert listed[0]["growing_unit_id"] == unit.id
