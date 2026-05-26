import pytest
from app.models import Photo, PhotoNote


def _photo(db_session, stem="2026-05-26T100000Z"):
    from datetime import datetime, timezone
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


def _note(db_session, photo_id, note_text="test note", x=0.5, y=0.5, x2=None, y2=None):
    note = PhotoNote(photo_id=photo_id, note_text=note_text, x=x, y=y, x2=x2, y2=y2)
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    return note


# --- POST /photos/{photo_id}/notes ---

def test_create_note_returns_201(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={"note_text": "hello", "x": 0.5, "y": 0.5})
    assert resp.status_code == 201


def test_create_note_response_fields(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={"note_text": "hello", "x": 0.25, "y": 0.75})
    data = resp.json()
    assert data["photo_id"] == photo.id
    assert data["note_text"] == "hello"
    assert data["x"] == 0.25
    assert data["y"] == 0.75
    assert data["x2"] is None
    assert data["y2"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_rect_note_returns_201(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes",
                       json={"note_text": "bad leaf", "x": 0.1, "y": 0.2, "x2": 0.4, "y2": 0.6})
    assert resp.status_code == 201


def test_create_rect_note_response_fields(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes",
                       json={"note_text": "pest", "x": 0.1, "y": 0.2, "x2": 0.4, "y2": 0.6})
    data = resp.json()
    assert data["x"] == 0.1
    assert data["y"] == 0.2
    assert data["x2"] == 0.4
    assert data["y2"] == 0.6


def test_create_rect_note_x2_out_of_range_returns_422(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes",
                       json={"note_text": "hi", "x": 0.1, "y": 0.2, "x2": 1.5, "y2": 0.6})
    assert resp.status_code == 422


def test_create_rect_note_x2_without_y2_returns_422(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes",
                       json={"note_text": "hi", "x": 0.1, "y": 0.2, "x2": 0.4})
    assert resp.status_code == 422


def test_create_rect_note_y2_without_x2_returns_422(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes",
                       json={"note_text": "hi", "x": 0.1, "y": 0.2, "y2": 0.6})
    assert resp.status_code == 422


def test_create_note_unknown_photo_returns_404(client):
    resp = client.post("/photos/99999/notes", json={"note_text": "hi", "x": 0.5, "y": 0.5})
    assert resp.status_code == 404


def test_create_note_x_out_of_range_returns_422(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={"note_text": "hi", "x": 1.5, "y": 0.5})
    assert resp.status_code == 422


def test_create_note_y_out_of_range_returns_422(client, db_session):
    photo = _photo(db_session)
    resp = client.post(f"/photos/{photo.id}/notes", json={"note_text": "hi", "x": 0.5, "y": -0.1})
    assert resp.status_code == 422


# --- GET /photos/{photo_id}/notes ---

def test_list_notes_empty(client, db_session):
    photo = _photo(db_session)
    assert client.get(f"/photos/{photo.id}/notes").json() == []


def test_list_notes_returns_notes(client, db_session):
    photo = _photo(db_session)
    _note(db_session, photo.id, "first")
    _note(db_session, photo.id, "second")
    data = client.get(f"/photos/{photo.id}/notes").json()
    assert len(data) == 2
    texts = {n["note_text"] for n in data}
    assert texts == {"first", "second"}


def test_list_notes_unknown_photo_returns_404(client):
    assert client.get("/photos/99999/notes").status_code == 404


def test_list_notes_only_returns_notes_for_that_photo(client, db_session):
    photo_a = _photo(db_session, "2026-05-26T100000Z")
    photo_b = _photo(db_session, "2026-05-26T110000Z")
    _note(db_session, photo_a.id, "note on A")
    _note(db_session, photo_b.id, "note on B")
    data = client.get(f"/photos/{photo_a.id}/notes").json()
    assert len(data) == 1
    assert data[0]["note_text"] == "note on A"


# --- PUT /notes/{note_id} ---

def test_update_note_text(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id, "original")
    resp = client.put(f"/notes/{note.id}", json={"note_text": "updated"})
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "updated"


def test_update_note_position(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id, x=0.1, y=0.2)
    resp = client.put(f"/notes/{note.id}", json={"x": 0.8, "y": 0.9})
    assert resp.status_code == 200
    data = resp.json()
    assert data["x"] == 0.8
    assert data["y"] == 0.9


def test_update_note_adds_rect(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    resp = client.put(f"/notes/{note.id}", json={"x2": 0.7, "y2": 0.8})
    assert resp.status_code == 200
    data = resp.json()
    assert data["x2"] == 0.7
    assert data["y2"] == 0.8


def test_update_note_rect_x2_without_y2_returns_422(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    assert client.put(f"/notes/{note.id}", json={"x2": 0.7}).status_code == 422


def test_update_note_sets_updated_at(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    resp = client.put(f"/notes/{note.id}", json={"note_text": "changed"})
    data = resp.json()
    assert data["updated_at"] >= data["created_at"]


def test_update_note_unknown_returns_404(client):
    assert client.put("/notes/99999", json={"note_text": "x"}).status_code == 404


def test_update_note_x_out_of_range_returns_422(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    assert client.put(f"/notes/{note.id}", json={"x": 2.0}).status_code == 422


# --- DELETE /notes/{note_id} ---

def test_delete_note_returns_204(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    assert client.delete(f"/notes/{note.id}").status_code == 204


def test_delete_note_removes_it(client, db_session):
    photo = _photo(db_session)
    note = _note(db_session, photo.id)
    client.delete(f"/notes/{note.id}")
    assert client.get(f"/photos/{photo.id}/notes").json() == []


def test_delete_note_unknown_returns_404(client):
    assert client.delete("/notes/99999").status_code == 404
