"""
Multi-step workflow tests. Each test exercises a complete user flow via the API
rather than testing individual endpoints in isolation.
"""


def _manual_upload(client, **fields):
    return client.post("/manual-photos", data=fields, files={
        "image": ("IMG_001.jpg", b"FAKEIMAGE", "image/jpeg"),
    })


# ── Photo classification workflow ─────────────────────────


def test_classify_photo_all_fields_reflected_in_listing(client):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    unit = client.post("/growing-units", json={"name": "Thai basil"}).json()

    photo = _manual_upload(client).json()
    r = client.put(f"/photos/{photo['id']}", json={
        "photo_type": "closeup",
        "location_id": loc["id"],
        "growing_unit_ids": [unit["id"]],
    })
    assert r.status_code == 200

    listing = client.get("/photos").json()
    p = next(x for x in listing if x["id"] == photo["id"])
    assert p["photo_type"] == "closeup"
    assert p["location_id"] == loc["id"]
    assert any(u["id"] == unit["id"] for u in p["growing_units"])


def test_reclassify_replaces_growing_units(client):
    u1 = client.post("/growing-units", json={"name": "Basil A"}).json()
    u2 = client.post("/growing-units", json={"name": "Basil B"}).json()

    photo = _manual_upload(client).json()
    client.put(f"/photos/{photo['id']}", json={"growing_unit_ids": [u1["id"]]})
    client.put(f"/photos/{photo['id']}", json={"growing_unit_ids": [u2["id"]]})

    listing = client.get("/photos").json()
    p = next(x for x in listing if x["id"] == photo["id"])
    unit_ids = {u["id"] for u in p["growing_units"]}
    assert unit_ids == {u2["id"]}


def test_clear_growing_units_via_empty_array(client):
    unit = client.post("/growing-units", json={"name": "Thai basil"}).json()

    photo = _manual_upload(client).json()
    client.put(f"/photos/{photo['id']}", json={"growing_unit_ids": [unit["id"]]})
    client.put(f"/photos/{photo['id']}", json={"growing_unit_ids": []})

    listing = client.get("/photos").json()
    p = next(x for x in listing if x["id"] == photo["id"])
    assert p["growing_units"] == []


# ── Label lifecycle ───────────────────────────────────────


def test_create_assign_and_remove_label_reflected_in_listing(client):
    photo = _manual_upload(client).json()

    label = client.post("/labels", json={"name": "rust"}).json()
    client.post(f"/photos/{photo['id']}/labels/{label['id']}")

    listing = client.get("/photos").json()
    p = next(x for x in listing if x["id"] == photo["id"])
    assert any(l["name"] == "rust" for l in p["labels"])

    client.delete(f"/photos/{photo['id']}/labels/{label['id']}")
    listing = client.get("/photos").json()
    p = next(x for x in listing if x["id"] == photo["id"])
    assert not any(l["name"] == "rust" for l in p["labels"])


# ── Event with full associations ─────────────────────────


def test_event_links_photo_location_and_unit(client):
    loc = client.post("/locations", json={"name": "Greenhouse"}).json()
    unit = client.post("/growing-units", json={"name": "Pepper plant"}).json()
    photo = _manual_upload(client).json()

    r = client.post("/events", json={
        "event_type": "watered",
        "location_id": loc["id"],
        "growing_unit_ids": [unit["id"]],
        "photo_ids": [photo["id"]],
        "note_text": "thorough watering",
    })
    assert r.status_code == 201
    event = r.json()
    assert event["location_id"] == loc["id"]
    assert any(u["id"] == unit["id"] for u in event["growing_units"])
    assert any(p["id"] == photo["id"] for p in event["photos"])
    assert event["note_text"] == "thorough watering"


def test_event_appears_in_get_events(client):
    r = client.post("/events", json={"event_type": "harvested", "note_text": "big yield"})
    event_id = r.json()["id"]

    events = client.get("/events").json()
    assert any(e["id"] == event_id for e in events)


# ── Listing filters ───────────────────────────────────────


def test_filter_by_location_returns_only_matching_photos(client):
    loc_a = client.post("/locations", json={"name": "Balcony"}).json()
    loc_b = client.post("/locations", json={"name": "Windowsill"}).json()

    photo_a = _manual_upload(client, location_id=loc_a["id"]).json()
    photo_b = client.post("/manual-photos", data={"location_id": loc_b["id"]}, files={
        "image": ("IMG_002.jpg", b"FAKEIMAGE", "image/jpeg"),
    }).json()

    results = client.get(f"/photos?location_id={loc_a['id']}").json()
    ids = {p["id"] for p in results}
    assert photo_a["id"] in ids
    assert photo_b["id"] not in ids


def test_filter_by_growing_unit_returns_only_matching_photos(client):
    u1 = client.post("/growing-units", json={"name": "Basil A"}).json()
    u2 = client.post("/growing-units", json={"name": "Basil B"}).json()

    photo_a = _manual_upload(client).json()
    photo_b = client.post("/manual-photos", data={}, files={
        "image": ("IMG_002.jpg", b"FAKEIMAGE", "image/jpeg"),
    }).json()

    client.put(f"/photos/{photo_a['id']}", json={"growing_unit_ids": [u1["id"]]})
    client.put(f"/photos/{photo_b['id']}", json={"growing_unit_ids": [u2["id"]]})

    results = client.get(f"/photos?growing_unit_id={u1['id']}").json()
    ids = {p["id"] for p in results}
    assert photo_a["id"] in ids
    assert photo_b["id"] not in ids
