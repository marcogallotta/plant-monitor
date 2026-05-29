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


# ── Relationship eager-load regression ───────────────────
# Each endpoint that serialises PhotoOut/EventOut must return full
# location_name, growing_units, and labels without N+1 queries.
# lazy="raise" on the model relationships guarantees a missed
# selectinload surfaces here as an exception rather than a silent
# performance regression.


def _setup_rich_fixtures(client):
    """Return (loc, unit1, unit2, label, photos, event) fully associated."""
    loc = client.post("/locations", json={"name": "South Window"}).json()
    unit1 = client.post("/growing-units", json={"name": "Basil A"}).json()
    unit2 = client.post("/growing-units", json={"name": "Mint B"}).json()
    label = client.post("/labels", json={"name": "new_growth"}).json()

    def upload(name):
        r = client.post("/manual-photos",
                        data={"location_id": loc["id"]},
                        files={"image": (name, b"FAKEIMAGE", "image/jpeg")})
        assert r.status_code == 201
        return r.json()

    p1 = upload("IMG_001.jpg")
    p2 = upload("IMG_002.jpg")
    p3 = upload("IMG_003.jpg")

    for p in (p1, p2, p3):
        client.put(f"/photos/{p['id']}", json={"growing_unit_ids": [unit1["id"], unit2["id"]]})
        client.post(f"/photos/{p['id']}/labels/{label['id']}")

    event_r = client.post("/events", json={
        "event_type": "watered",
        "location_id": loc["id"],
        "growing_unit_ids": [unit1["id"], unit2["id"]],
        "photo_ids": [p1["id"], p2["id"]],
    })
    assert event_r.status_code == 201
    event = event_r.json()

    return loc, unit1, unit2, label, (p1, p2, p3), event


def _assert_photo_shape(p, loc, unit1, unit2, label):
    assert p["location_name"] == loc["name"]
    unit_ids = {u["id"] for u in p["growing_units"]}
    assert unit1["id"] in unit_ids
    assert unit2["id"] in unit_ids
    assert any(l["id"] == label["id"] for l in p["labels"])


def _assert_event_shape(e, loc, unit1, unit2):
    assert e["location_name"] == loc["name"]
    unit_ids = {u["id"] for u in e["growing_units"]}
    assert unit1["id"] in unit_ids
    assert unit2["id"] in unit_ids


def test_list_photos_includes_all_related_data(client):
    loc, unit1, unit2, label, (p1, p2, p3), _ = _setup_rich_fixtures(client)
    photos = client.get("/photos").json()
    for pid in (p1["id"], p2["id"], p3["id"]):
        p = next(x for x in photos if x["id"] == pid)
        _assert_photo_shape(p, loc, unit1, unit2, label)


def test_list_events_includes_all_related_data(client):
    loc, unit1, unit2, label, (p1, p2, _), event = _setup_rich_fixtures(client)
    events = client.get("/events").json()
    e = next(x for x in events if x["id"] == event["id"])
    _assert_event_shape(e, loc, unit1, unit2)
    assert any(p["id"] == p1["id"] for p in e["photos"])
    assert any(p["id"] == p2["id"] for p in e["photos"])


def test_classify_photo_response_includes_all_related_data(client):
    loc = client.post("/locations", json={"name": "Shelf"}).json()
    unit = client.post("/growing-units", json={"name": "Chilli"}).json()
    photo = client.post("/manual-photos", files={"image": ("x.jpg", b"FAKEIMAGE", "image/jpeg")}).json()
    r = client.put(f"/photos/{photo['id']}", json={
        "location_id": loc["id"],
        "growing_unit_ids": [unit["id"]],
    })
    assert r.status_code == 200
    p = r.json()
    assert p["location_name"] == loc["name"]
    assert any(u["id"] == unit["id"] for u in p["growing_units"])


def test_assign_label_response_includes_all_related_data(client):
    loc = client.post("/locations", json={"name": "Shelf"}).json()
    photo = client.post("/manual-photos",
                        data={"location_id": loc["id"]},
                        files={"image": ("x.jpg", b"FAKEIMAGE", "image/jpeg")}).json()
    label = client.post("/labels", json={"name": "recovery"}).json()
    r = client.post(f"/photos/{photo['id']}/labels/{label['id']}")
    assert r.status_code == 200
    p = r.json()
    assert p["location_name"] == loc["name"]
    assert any(l["id"] == label["id"] for l in p["labels"])


def test_create_event_response_includes_all_related_data(client):
    loc, unit1, unit2, _, (p1, _, _), event = _setup_rich_fixtures(client)
    _assert_event_shape(event, loc, unit1, unit2)
    assert any(p["id"] == p1["id"] for p in event["photos"])
