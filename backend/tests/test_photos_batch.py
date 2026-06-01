"""Tests for POST /photos/batch — apply edits to many photos at once."""

import json as _json


def _make_photo(client, stem):
    meta = _json.dumps({"captured_at": "2026-05-28T12:00:00Z", "filename": f"{stem}.jpg"}).encode()
    client.post("/photos", files={
        "image":    (f"{stem}.jpg", b"FAKEIMAGE", "image/jpeg"),
        "metadata": (f"{stem}.json", meta, "application/json"),
    })


def _two_photos(client):
    _make_photo(client, "2026-05-28T120000Z")
    _make_photo(client, "2026-05-28T130000Z")
    return client.get("/photos").json()["photos"]


def test_batch_requires_non_empty_ids(client):
    r = client.post("/photos/batch", json={"ids": []})
    assert r.status_code == 422


def test_batch_unknown_id_returns_404(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [photos[0]["id"], 999999]
    r = client.post("/photos/batch", json={"ids": ids, "photo_type": "overview"})
    assert r.status_code == 404
    assert "999999" in r.json()["detail"]


def test_batch_sets_photo_type_on_all(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    r = client.post("/photos/batch", json={"ids": ids, "photo_type": "harvest"})
    assert r.status_code == 200
    assert {p["photo_type"] for p in r.json()} == {"harvest"}
    for p in client.get("/photos").json()["photos"]:
        assert p["photo_type"] == "harvest"


def test_batch_sets_location_on_all(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    r = client.post("/photos/batch", json={"ids": ids, "location_id": loc["id"]})
    assert r.status_code == 200
    assert {p["location_id"] for p in r.json()} == {loc["id"]}


def test_batch_unknown_location_returns_404(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    r = client.post("/photos/batch", json={"ids": ids, "location_id": 999999})
    assert r.status_code == 404


def test_batch_omitted_fields_are_untouched(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    loc = client.post("/locations", json={"name": "Sill"}).json()
    client.post("/photos/batch", json={"ids": ids, "location_id": loc["id"]})
    # A subsequent batch that only sets photo_type must not clear location.
    r = client.post("/photos/batch", json={"ids": ids, "photo_type": "overview"})
    assert {p["location_id"] for p in r.json()} == {loc["id"]}


def test_batch_omitting_photo_type_preserves_it(client, isolated_photos_dir):
    # The model_fields_set distinction: {"photo_type": null} clears, but a body
    # that omits photo_type entirely must leave the existing value untouched.
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    loc = client.post("/locations", json={"name": "Bench"}).json()
    client.post("/photos/batch", json={"ids": ids, "photo_type": "harvest"})
    # Second call sets only location; photo_type is absent from the body.
    r = client.post("/photos/batch", json={"ids": ids, "location_id": loc["id"]})
    assert {p["photo_type"] for p in r.json()} == {"harvest"}


def test_batch_can_clear_photo_type_with_null(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    client.post("/photos/batch", json={"ids": ids, "photo_type": "overview"})
    r = client.post("/photos/batch", json={"ids": ids, "photo_type": None})
    assert {p["photo_type"] for p in r.json()} == {None}


def test_batch_add_units_merges_without_removing(client, isolated_photos_dir):
    photos = _two_photos(client)
    p0, p1 = photos[0]["id"], photos[1]["id"]
    u1 = client.post("/growing-units", json={"name": "Basil 1"}).json()
    u2 = client.post("/growing-units", json={"name": "Mint 1"}).json()
    # p0 already has u1 assigned via the single-photo path.
    client.put(f"/photos/{p0}", json={"growing_unit_ids": [u1["id"]]})
    r = client.post("/photos/batch", json={"ids": [p0, p1], "add_unit_ids": [u2["id"]]})
    by_id = {p["id"]: p for p in r.json()}
    assert {u["id"] for u in by_id[p0]["growing_units"]} == {u1["id"], u2["id"]}
    assert {u["id"] for u in by_id[p1]["growing_units"]} == {u2["id"]}


def test_batch_add_units_is_idempotent(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    u1 = client.post("/growing-units", json={"name": "Dill 1"}).json()
    client.post("/photos/batch", json={"ids": ids, "add_unit_ids": [u1["id"]]})
    r = client.post("/photos/batch", json={"ids": ids, "add_unit_ids": [u1["id"]]})
    for p in r.json():
        assert [u["id"] for u in p["growing_units"]] == [u1["id"]]


def test_batch_duplicate_unit_ids_in_request_is_safe(client, isolated_photos_dir):
    # Duplicate ids in add_unit_ids must not queue two inserts (composite PK → would 500).
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    u1 = client.post("/growing-units", json={"name": "Thyme 1"}).json()
    r = client.post("/photos/batch", json={"ids": ids, "add_unit_ids": [u1["id"], u1["id"]]})
    assert r.status_code == 200
    for p in r.json():
        assert [u["id"] for u in p["growing_units"]] == [u1["id"]]


def test_batch_duplicate_label_ids_in_request_is_safe(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    lid = client.get("/labels").json()[0]["id"]
    r = client.post("/photos/batch", json={"ids": ids, "add_label_ids": [lid, lid]})
    assert r.status_code == 200
    for p in r.json():
        assert [l["id"] for l in p["labels"]] == [lid]


def test_batch_unknown_unit_returns_404(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    r = client.post("/photos/batch", json={"ids": ids, "add_unit_ids": [999999]})
    assert r.status_code == 404


def test_batch_add_labels_merges_and_is_idempotent(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    labels = client.get("/labels").json()
    lid = labels[0]["id"]
    client.post(f"/photos/{ids[0]}/labels/{lid}")  # pre-assign to one
    r = client.post("/photos/batch", json={"ids": ids, "add_label_ids": [lid]})
    for p in r.json():
        assert [l["id"] for l in p["labels"]] == [lid]
    # idempotent re-apply
    r2 = client.post("/photos/batch", json={"ids": ids, "add_label_ids": [lid]})
    for p in r2.json():
        assert [l["id"] for l in p["labels"]] == [lid]


def test_batch_unknown_label_returns_404(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    r = client.post("/photos/batch", json={"ids": ids, "add_label_ids": [999999]})
    assert r.status_code == 404


def test_batch_combined_fields_in_one_call(client, isolated_photos_dir):
    photos = _two_photos(client)
    ids = [p["id"] for p in photos]
    loc = client.post("/locations", json={"name": "Rail"}).json()
    unit = client.post("/growing-units", json={"name": "Sage 1"}).json()
    lid = client.get("/labels").json()[0]["id"]
    r = client.post("/photos/batch", json={
        "ids": ids,
        "photo_type": "closeup",
        "location_id": loc["id"],
        "add_unit_ids": [unit["id"]],
        "add_label_ids": [lid],
    })
    assert r.status_code == 200
    for p in r.json():
        assert p["photo_type"] == "closeup"
        assert p["location_id"] == loc["id"]
        assert [u["id"] for u in p["growing_units"]] == [unit["id"]]
        assert [l["id"] for l in p["labels"]] == [lid]
