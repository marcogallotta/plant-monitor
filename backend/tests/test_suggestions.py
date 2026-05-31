from datetime import datetime, timezone

from app.models import Photo, PhotoAiSuggestion


def _photo(db_session, filename="2026-05-26T100000Z.jpg"):
    photo = Photo(
        filename=filename,
        captured_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        storage_path=f"/tmp/{filename}",
        metadata_path=f"/tmp/{filename}.json",
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def _suggestion(db_session, photo_id, **kwargs):
    s = PhotoAiSuggestion(photo_id=photo_id, model="claude-sonnet-4-6", **kwargs)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def test_list_suggestions_empty(client, db_session):
    resp = client.get("/suggestions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_suggestions_returns_pending(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, suggested_plant_name="Sorrel", confidence="high")
    resp = client.get("/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["suggested_plant_name"] == "Sorrel"
    assert data[0]["status"] == "pending"


def test_list_suggestions_includes_photo_fields(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id)
    data = client.get("/suggestions").json()
    assert data[0]["photo_id"] == photo.id
    assert data[0]["photo_url"] == f"/photos/{photo.filename}"
    assert "photo_captured_at" in data[0]


def test_list_suggestions_excludes_non_pending(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, status="accepted")
    resp = client.get("/suggestions")
    assert resp.json() == []


def test_list_suggestions_filter_by_status(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, status="accepted", suggested_plant_name="Dill")
    data = client.get("/suggestions?status=accepted").json()
    assert len(data) == 1
    assert data[0]["suggested_plant_name"] == "Dill"


def test_list_suggestions_invalid_status(client, db_session):
    resp = client.get("/suggestions?status=bogus")
    assert resp.status_code == 422


def test_list_suggestions_ordered_by_created_at(client, db_session):
    photo = _photo(db_session)
    s1 = _suggestion(db_session, photo.id, suggested_plant_name="First")
    s2 = _suggestion(db_session, photo.id, suggested_plant_name="Second")
    data = client.get("/suggestions").json()
    ids = [d["id"] for d in data]
    assert ids == [s1.id, s2.id]


def test_list_suggestions_includes_region_fields(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, x=0.0, y=0.0, x2=0.5, y2=1.0)
    data = client.get("/suggestions").json()
    assert data[0]["x"] == 0.0
    assert data[0]["x2"] == 0.5
