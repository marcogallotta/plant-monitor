import pytest


def _photo(client, isolated_photos_dir):
    import json as _json
    stem = "2026-05-26T100000Z"
    meta = _json.dumps({"captured_at": "2026-05-26T10:00:00Z", "filename": f"{stem}.jpg"}).encode()
    client.post("/photos", files={
        "image":    (f"{stem}.jpg", b"FAKEIMAGE", "image/jpeg"),
        "metadata": (f"{stem}.json", meta, "application/json"),
    })
    return client.get("/photos").json()[0]


# --- POST /events ---

def test_create_event_returns_201(client):
    r = client.post("/events", json={"event_type": "watered"})
    assert r.status_code == 201


def test_create_event_response_fields(client):
    r = client.post("/events", json={"event_type": "harvested", "note_text": "Basil harvest"})
    data = r.json()
    assert data["event_type"] == "harvested"
    assert data["note_text"] == "Basil harvest"
    assert "id" in data
    assert "event_at" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_event_defaults_event_at_to_now(client):
    r = client.post("/events", json={"event_type": "watered"})
    assert r.json()["event_at"] is not None


def test_create_event_accepts_event_at(client):
    r = client.post("/events", json={"event_type": "watered", "event_at": "2026-05-26T09:00:00Z"})
    assert "2026-05-26" in r.json()["event_at"]


def test_create_event_event_type_required(client):
    r = client.post("/events", json={"note_text": "no type"})
    assert r.status_code == 422


def test_create_event_with_location(client):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    r = client.post("/events", json={"event_type": "watered", "location_id": loc["id"]})
    assert r.status_code == 201
    assert r.json()["location_id"] == loc["id"]
    assert r.json()["location_name"] == "Balcony"


def test_create_event_bad_location_returns_404(client):
    r = client.post("/events", json={"event_type": "watered", "location_id": 99999})
    assert r.status_code == 404


def test_create_event_links_growing_units(client):
    u1 = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    u2 = client.post("/growing-units", json={"name": "Genovese basil plant 1"}).json()
    r = client.post("/events", json={
        "event_type": "watered",
        "growing_unit_ids": [u1["id"], u2["id"]],
    })
    assert r.status_code == 201
    unit_ids = {u["id"] for u in r.json()["growing_units"]}
    assert unit_ids == {u1["id"], u2["id"]}


def test_create_event_bad_growing_unit_returns_404(client):
    r = client.post("/events", json={"event_type": "watered", "growing_unit_ids": [99999]})
    assert r.status_code == 404


def test_create_event_links_photos(client, isolated_photos_dir):
    photo = _photo(client, isolated_photos_dir)
    r = client.post("/events", json={"event_type": "harvested", "photo_ids": [photo["id"]]})
    assert r.status_code == 201
    assert any(p["id"] == photo["id"] for p in r.json()["photos"])


def test_create_event_bad_photo_returns_404(client):
    r = client.post("/events", json={"event_type": "watered", "photo_ids": [99999]})
    assert r.status_code == 404


def test_create_event_optional_fields_null(client):
    r = client.post("/events", json={"event_type": "other"})
    data = r.json()
    assert data["note_text"] is None
    assert data["location_id"] is None
    assert data["growing_units"] == []
    assert data["photos"] == []


# --- GET /events ---

def test_list_events_empty(client):
    r = client.get("/events")
    assert r.status_code == 200
    assert r.json() == []


def test_list_events_returns_all(client):
    client.post("/events", json={"event_type": "watered"})
    client.post("/events", json={"event_type": "harvested"})
    r = client.get("/events")
    types = [e["event_type"] for e in r.json()]
    assert "watered" in types
    assert "harvested" in types


def test_list_events_ordered_by_event_at_desc(client):
    client.post("/events", json={"event_type": "watered",   "event_at": "2026-05-26T08:00:00Z"})
    client.post("/events", json={"event_type": "harvested", "event_at": "2026-05-26T10:00:00Z"})
    events = client.get("/events").json()
    assert events[0]["event_type"] == "harvested"
    assert events[1]["event_type"] == "watered"
