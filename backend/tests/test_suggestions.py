from datetime import datetime, timezone

from app.models import GrowingUnit, Label, Photo, PhotoAiSuggestion, PhotoGrowingUnit, PhotoLabel


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


# --- list ---

def test_list_suggestions_empty(client, db_session):
    resp = client.get("/suggestions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_suggestions_returns_pending(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, suggested_plant_name="Sorrel", confidence="high")
    data = client.get("/suggestions").json()
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
    assert client.get("/suggestions").json() == []


def test_list_suggestions_filter_by_status(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, status="accepted", suggested_plant_name="Dill")
    data = client.get("/suggestions?status=accepted").json()
    assert len(data) == 1
    assert data[0]["suggested_plant_name"] == "Dill"


def test_list_suggestions_invalid_status(client, db_session):
    assert client.get("/suggestions?status=bogus").status_code == 422


def test_list_suggestions_ordered_by_created_at(client, db_session):
    photo = _photo(db_session)
    s1 = _suggestion(db_session, photo.id, suggested_plant_name="First")
    s2 = _suggestion(db_session, photo.id, suggested_plant_name="Second")
    ids = [d["id"] for d in client.get("/suggestions").json()]
    assert ids == [s1.id, s2.id]


def test_list_suggestions_includes_region_fields(client, db_session):
    photo = _photo(db_session)
    _suggestion(db_session, photo.id, x=0.0, y=0.0, x2=0.5, y2=1.0)
    data = client.get("/suggestions").json()
    assert data[0]["x"] == 0.0
    assert data[0]["x2"] == 0.5


# --- resolve ---

def test_resolve_unknown_returns_404(client, db_session):
    assert client.patch("/suggestions/99999", json={"action": "accept"}).status_code == 404


def test_resolve_invalid_action_returns_422(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id)
    assert client.patch(f"/suggestions/{s.id}", json={"action": "bogus"}).status_code == 422


def test_resolve_reject(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id)
    resp = client.patch(f"/suggestions/{s.id}", json={"action": "reject"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    db_session.refresh(s)
    assert s.status == "rejected"
    assert s.reviewed_at is not None


def test_resolve_accept_sets_photo_type(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_photo_type="health_check")
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    db_session.refresh(photo)
    assert photo.photo_type == "health_check"


def test_resolve_accept_sets_rotation(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_rotation=90)
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    db_session.refresh(photo)
    assert photo.rotation == 90


def test_resolve_accept_links_existing_unit(client, db_session):
    photo = _photo(db_session)
    unit = GrowingUnit(name="Sorrel")
    db_session.add(unit)
    db_session.commit()
    s = _suggestion(db_session, photo.id, suggested_plant_id=unit.id)
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    assert db_session.query(PhotoGrowingUnit).filter_by(photo_id=photo.id, growing_unit_id=unit.id).count() == 1


def test_resolve_accept_creates_unit_from_name(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_plant_name="New Herb")
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    unit = db_session.query(GrowingUnit).filter_by(name="New Herb").first()
    assert unit is not None
    assert db_session.query(PhotoGrowingUnit).filter_by(photo_id=photo.id, growing_unit_id=unit.id).count() == 1


def test_resolve_accept_reuses_existing_unit_by_name(client, db_session):
    photo = _photo(db_session)
    unit = GrowingUnit(name="Sorrel")
    db_session.add(unit)
    db_session.commit()
    s = _suggestion(db_session, photo.id, suggested_plant_name="Sorrel")
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    assert db_session.query(GrowingUnit).filter_by(name="Sorrel").count() == 1


def test_resolve_accept_creates_and_assigns_labels(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_labels=["wilting", "new growth"])
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    labels = db_session.query(Label).all()
    label_names = {l.name for l in labels}
    assert "wilting" in label_names
    assert "new_growth" in label_names
    assert db_session.query(PhotoLabel).filter_by(photo_id=photo.id).count() == 2


def test_resolve_accept_idempotent_label_assign(client, db_session):
    photo = _photo(db_session)
    label = db_session.query(Label).filter_by(name="aphids").first()
    db_session.add(PhotoLabel(photo_id=photo.id, label_id=label.id))
    db_session.commit()
    s = _suggestion(db_session, photo.id, suggested_labels=["aphids"])
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    assert db_session.query(PhotoLabel).filter_by(photo_id=photo.id, label_id=label.id).count() == 1


def test_resolve_accept_marks_suggestion(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id)
    client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    db_session.refresh(s)
    assert s.status == "accepted"
    assert s.reviewed_at is not None


def test_resolve_accept_with_overrides_marks_edited(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_plant_name="Dill", suggested_photo_type="overview", suggested_labels=["wilting"])
    resp = client.patch(f"/suggestions/{s.id}", json={
        "action": "accept",
        "edited_plant_name": "Mint",
        "edited_photo_type": "health_check",
        "edited_labels": ["new_growth"],
    })
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.status == "edited"
    assert s.reviewed_at is not None
    unit = db_session.query(GrowingUnit).filter_by(name="Mint").first()
    assert unit is not None
    assert s.edited_plant_id == unit.id
    assert s.edited_photo_type == "health_check"
    assert s.edited_labels == ["new_growth"]
    db_session.refresh(photo)
    assert photo.photo_type == "health_check"


def test_resolve_accept_without_overrides_marks_accepted(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_plant_name="Dill")
    resp = client.patch(f"/suggestions/{s.id}", json={"action": "accept"})
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.status == "accepted"
    assert s.edited_plant_id is None
    assert s.edited_photo_type is None
    assert s.edited_labels is None


def test_resolve_accept_only_labels_overridden_does_not_set_edited_plant_id(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id, suggested_plant_name="Dill", suggested_labels=["wilting"])
    client.patch(f"/suggestions/{s.id}", json={"action": "accept", "edited_labels": ["new_growth"]})
    db_session.refresh(s)
    assert s.status == "edited"
    assert s.edited_plant_id is None
    assert s.edited_labels == ["new_growth"]


def test_resolve_deleted_removes_photo(client, db_session):
    photo = _photo(db_session)
    s = _suggestion(db_session, photo.id)
    resp = client.patch(f"/suggestions/{s.id}", json={"action": "deleted"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert db_session.query(Photo).filter_by(id=photo.id).first() is None
