import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main
import app.routers.assistant
from app.database import get_db
from app.main import app as fastapi_app
from app.models import (
    Event, EventGrowingUnit, EventPhoto,
    GrowingUnit, Location, Photo, PhotoGrowingUnit, PhotoNote,
)

_TOKEN = "test-assistant-token"


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("ASSISTANT_API_TOKEN", _TOKEN)

    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app, headers={"Authorization": f"Bearer {_TOKEN}"})
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(db_session, monkeypatch):
    monkeypatch.setenv("ASSISTANT_API_TOKEN", _TOKEN)

    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


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


def _event(db, event_type="watered", location_id=None):
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


def test_assistant_photos_filter_end(client, db_session):
    _photo(db_session, "2026-05-26T090000Z")
    _photo(db_session, "2026-05-26T110000Z")
    data = client.get("/assistant/photos?end=2026-05-26T10:00:00Z").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T090000Z.jpg"


def test_assistant_photos_filter_photo_type(client, db_session):
    _photo(db_session, "2026-05-26T090000Z", photo_type="overview")
    _photo(db_session, "2026-05-26T110000Z", photo_type="closeup")
    data = client.get("/assistant/photos?photo_type=overview").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T090000Z.jpg"


def test_assistant_photos_filter_location_id(client, db_session):
    loc = _location(db_session)
    _photo(db_session, "2026-05-26T090000Z", location_id=loc.id)
    _photo(db_session, "2026-05-26T110000Z")
    data = client.get(f"/assistant/photos?location_id={loc.id}").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T090000Z.jpg"


def test_assistant_photos_filter_growing_unit_id(client, db_session):
    unit = _growing_unit(db_session)
    photo_with = _photo(db_session, "2026-05-26T090000Z")
    _photo(db_session, "2026-05-26T110000Z")
    db_session.add(PhotoGrowingUnit(photo_id=photo_with.id, growing_unit_id=unit.id))
    db_session.commit()
    data = client.get(f"/assistant/photos?growing_unit_id={unit.id}").json()
    assert len(data) == 1
    assert data[0]["filename"] == "2026-05-26T090000Z.jpg"


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
    assert data["events"][0]["event_type"] == "watered"


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
    assert data["events"][0]["event_type"] == "watered"


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
    assert data[0]["event_type"] == "watered"


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


# --- Auth ---

def test_no_token_returns_401(unauth_client):
    assert unauth_client.get("/assistant/summary").status_code == 401


def test_wrong_token_returns_401(db_session, monkeypatch):
    monkeypatch.setenv("ASSISTANT_API_TOKEN", _TOKEN)

    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        tc = TestClient(fastapi_app, headers={"Authorization": "Bearer wrong-token"})
        assert tc.get("/assistant/summary").status_code == 401
    finally:
        fastapi_app.dependency_overrides.clear()


def test_token_not_configured_returns_503(db_session, monkeypatch):
    monkeypatch.delenv("ASSISTANT_API_TOKEN", raising=False)

    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        tc = TestClient(fastapi_app, headers={"Authorization": "Bearer anything"})
        assert tc.get("/assistant/summary").status_code == 503
    finally:
        fastapi_app.dependency_overrides.clear()


def test_auth_does_not_affect_non_assistant_routes(unauth_client):
    assert unauth_client.get("/photos").status_code == 200


# --- Rate limiting ---

@pytest.fixture(autouse=True)
def reset_rate_limit():
    app.routers.assistant._rate_limit_store.clear()
    yield
    app.routers.assistant._rate_limit_store.clear()


def test_rate_limit_allows_requests_under_limit(client, monkeypatch):
    monkeypatch.setattr(app.routers.assistant, "_RATE_LIMIT", 3)
    for _ in range(3):
        assert client.get("/assistant/summary").status_code == 200


def test_rate_limit_blocks_when_exceeded(client, monkeypatch):
    monkeypatch.setattr(app.routers.assistant, "_RATE_LIMIT", 3)
    for _ in range(3):
        client.get("/assistant/summary")
    resp = client.get("/assistant/summary")
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == str(app.routers.assistant._RATE_WINDOW)


def test_rate_limit_resets_after_window(client, monkeypatch):
    monkeypatch.setattr(app.routers.assistant, "_RATE_LIMIT", 2)
    for _ in range(2):
        client.get("/assistant/summary")
    assert client.get("/assistant/summary").status_code == 429
    # Backdate the window start to simulate expiry
    count, window_start = app.routers.assistant._rate_limit_store[_TOKEN]
    app.routers.assistant._rate_limit_store[_TOKEN] = (count, window_start - app.routers.assistant._RATE_WINDOW - 1)
    assert client.get("/assistant/summary").status_code == 200


def test_rate_limit_does_not_apply_to_other_routes(client, monkeypatch):
    monkeypatch.setattr(app.routers.assistant, "_RATE_LIMIT", 1)
    client.get("/assistant/summary")
    assert client.get("/assistant/summary").status_code == 429


# ── Relationship eager-load regression (assistant endpoints) ──────────────
# These endpoints must serialise full PhotoOut/EventOut (location_name,
# growing_units, labels/photos) without hitting lazy-load paths.
# lazy="raise" on the model relationships turns any missed selectinload
# into an exception rather than a silent N+1.


def _setup_assistant_fixtures(client_api):
    loc_r = client_api.post("/locations", json={"name": "North Shelf"})
    assert loc_r.status_code == 201
    loc = loc_r.json()

    unit_r = client_api.post("/growing-units", json={"name": "Parsley"})
    assert unit_r.status_code == 201
    unit = unit_r.json()

    label_r = client_api.post("/labels", json={"name": "watch"})
    assert label_r.status_code == 200 or label_r.status_code == 201
    label = label_r.json()

    def upload(name):
        r = client_api.post("/manual-photos",
                             data={"location_id": loc["id"]},
                             files={"image": (name, b"FAKEIMAGE", "image/jpeg")})
        assert r.status_code == 201
        return r.json()

    p1 = upload("A.jpg")
    p2 = upload("B.jpg")

    for p in (p1, p2):
        client_api.put(f"/photos/{p['id']}", json={"growing_unit_ids": [unit["id"]]})
        client_api.post(f"/photos/{p['id']}/labels/{label['id']}")

    event_r = client_api.post("/events", json={
        "event_type": "fed_liquid",
        "location_id": loc["id"],
        "growing_unit_ids": [unit["id"]],
        "photo_ids": [p1["id"]],
    })
    assert event_r.status_code == 201
    event = event_r.json()

    return loc, unit, label, p1, p2, event


def test_assistant_list_photos_includes_related_data(client):
    loc, unit, label, p1, p2, _ = _setup_assistant_fixtures(client)
    photos = client.get("/assistant/photos").json()
    for pid in (p1["id"], p2["id"]):
        p = next(x for x in photos if x["id"] == pid)
        assert p["location_name"] == loc["name"]
        assert any(u["id"] == unit["id"] for u in p["growing_units"])
        assert any(l["id"] == label["id"] for l in p["labels"])


def test_assistant_get_photo_includes_related_data(client):
    loc, unit, label, p1, _, _ = _setup_assistant_fixtures(client)
    p = client.get(f"/assistant/photos/{p1['id']}").json()
    assert p["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in p["growing_units"])
    assert any(l["id"] == label["id"] for l in p["labels"])


def test_assistant_photo_context_includes_related_data(client):
    loc, unit, label, p1, _, event = _setup_assistant_fixtures(client)
    ctx = client.get(f"/assistant/photos/{p1['id']}/context").json()
    assert ctx["photo"]["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in ctx["photo"]["growing_units"])
    assert len(ctx["events"]) >= 1
    e = next(x for x in ctx["events"] if x["id"] == event["id"])
    assert e["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in e["growing_units"])


def test_assistant_growing_unit_context_includes_related_data(client):
    loc, unit, label, p1, p2, event = _setup_assistant_fixtures(client)
    ctx = client.get(f"/assistant/growing-units/{unit['id']}/context").json()
    photo_ids = {p["id"] for p in ctx["photos"]}
    assert p1["id"] in photo_ids
    assert p2["id"] in photo_ids
    for p in ctx["photos"]:
        assert p["location_name"] == loc["name"]
    event_ids = {e["id"] for e in ctx["events"]}
    assert event["id"] in event_ids
    e = next(x for x in ctx["events"] if x["id"] == event["id"])
    assert e["location_name"] == loc["name"]


def test_assistant_list_events_includes_related_data(client):
    loc, unit, label, p1, _, event = _setup_assistant_fixtures(client)
    events = client.get("/assistant/events").json()
    e = next(x for x in events if x["id"] == event["id"])
    assert e["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in e["growing_units"])
    assert any(p["id"] == p1["id"] for p in e["photos"])


def test_assistant_unclassified_includes_related_data(client):
    loc = client.post("/locations", json={"name": "Shelf"}).json()
    unit = client.post("/growing-units", json={"name": "Sage"}).json()
    p = client.post("/manual-photos",
                    data={"location_id": loc["id"]},
                    files={"image": ("u.jpg", b"FAKEIMAGE", "image/jpeg")}).json()
    client.put(f"/photos/{p['id']}", json={"growing_unit_ids": [unit["id"]]})
    # photo_type is None → unclassified
    unclassified = client.get("/assistant/unclassified").json()
    match = next((x for x in unclassified if x["id"] == p["id"]), None)
    assert match is not None
    assert match["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in match["growing_units"])


def test_assistant_summary_recent_photos_include_related_data(client):
    loc, unit, label, p1, _, _ = _setup_assistant_fixtures(client)
    summary = client.get("/assistant/summary").json()
    recent_ids = {p["id"] for p in summary["recent_photos"]}
    if p1["id"] in recent_ids:
        p = next(x for x in summary["recent_photos"] if x["id"] == p1["id"])
        assert p["location_name"] == loc["name"]
        assert any(u["id"] == unit["id"] for u in p["growing_units"])


def test_contact_sheet_invalid_ids_returns_422(client):
    r = client.get("/assistant/contact-sheet?ids=abc")
    assert r.status_code == 422


def test_contact_sheet_too_many_ids_returns_422(client):
    ids = ",".join(str(i) for i in range(1, 27))  # 26 ids
    r = client.get(f"/assistant/contact-sheet?ids={ids}")
    assert r.status_code == 422


def test_contact_sheet_missing_photo_still_returns_200(client, isolated_photos_dir):
    p = client.post("/manual-photos",
                    files={"image": ("x.jpg", b"FAKEIMAGE", "image/jpeg")}).json()
    real_id = p["id"]
    missing_id = real_id + 9999
    r = client.get(f"/assistant/contact-sheet?ids={real_id},{missing_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["photo_ids"] == [real_id, missing_id]
    assert "image_data_url" in body
    assert client.get("/photos").status_code == 200
