import pytest


def _make_photo(client, isolated_photos_dir):
    import json as _json
    stem = "2026-05-28T120000Z"
    meta = _json.dumps({"captured_at": "2026-05-28T12:00:00Z", "filename": f"{stem}.jpg"}).encode()
    client.post("/photos", files={
        "image":    (f"{stem}.jpg", b"FAKEIMAGE", "image/jpeg"),
        "metadata": (f"{stem}.json", meta, "application/json"),
    })
    return client.get("/photos").json()[0]


# --- GET /labels ---

def test_list_labels_returns_200(client):
    r = client.get("/labels")
    assert r.status_code == 200


def test_list_labels_returns_seeded_labels(client):
    labels = client.get("/labels").json()
    names = [l["name"] for l in labels]
    assert "aphids" in names
    assert "yellowing" in names


def test_list_labels_ordered_by_usage_count(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    labels = client.get("/labels").json()
    # pick a label that is not first by default and assign it to a photo
    target = labels[-1]
    client.post(f"/photos/{photo['id']}/labels/{target['id']}")
    refreshed = client.get("/labels").json()
    assert refreshed[0]["id"] == target["id"]


def test_list_labels_unused_labels_sorted_alphabetically(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    labels = client.get("/labels").json()
    # assign one label so it rises to top; rest should be alpha among themselves
    client.post(f"/photos/{photo['id']}/labels/{labels[0]['id']}")
    refreshed = client.get("/labels").json()
    unused = [l["name"] for l in refreshed[1:]]
    assert unused == sorted(unused)


def test_label_has_id_and_name(client):
    label = client.get("/labels").json()[0]
    assert "id" in label
    assert "name" in label


# --- POST /photos/{id}/labels/{label_id} ---

def test_assign_label_returns_200(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label_id = client.get("/labels").json()[0]["id"]
    r = client.post(f"/photos/{photo['id']}/labels/{label_id}")
    assert r.status_code == 200


def test_assign_label_appears_in_photo_labels(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label = client.get("/labels").json()[0]
    client.post(f"/photos/{photo['id']}/labels/{label['id']}")
    updated = client.get("/photos").json()[0]
    assert any(l["id"] == label["id"] for l in updated["labels"])


def test_assign_label_appears_in_get_photos(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label = client.get("/labels").json()[0]
    client.post(f"/photos/{photo['id']}/labels/{label['id']}")
    photos = client.get("/photos").json()
    match = next(p for p in photos if p["id"] == photo["id"])
    assert any(l["name"] == label["name"] for l in match["labels"])


def test_assign_label_bad_photo_returns_404(client):
    label_id = client.get("/labels").json()[0]["id"]
    r = client.post(f"/photos/99999/labels/{label_id}")
    assert r.status_code == 404


def test_assign_label_bad_label_returns_404(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    r = client.post(f"/photos/{photo['id']}/labels/99999")
    assert r.status_code == 404


def test_assign_label_duplicate_is_idempotent(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label_id = client.get("/labels").json()[0]["id"]
    client.post(f"/photos/{photo['id']}/labels/{label_id}")
    r = client.post(f"/photos/{photo['id']}/labels/{label_id}")
    assert r.status_code == 200
    updated = client.get("/photos").json()[0]
    assert len([l for l in updated["labels"] if l["id"] == label_id]) == 1


# --- DELETE /photos/{id}/labels/{label_id} ---

def test_remove_label_returns_204(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label_id = client.get("/labels").json()[0]["id"]
    client.post(f"/photos/{photo['id']}/labels/{label_id}")
    r = client.delete(f"/photos/{photo['id']}/labels/{label_id}")
    assert r.status_code == 204


def test_remove_label_no_longer_appears(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label = client.get("/labels").json()[0]
    client.post(f"/photos/{photo['id']}/labels/{label['id']}")
    client.delete(f"/photos/{photo['id']}/labels/{label['id']}")
    updated = client.get("/photos").json()[0]
    assert not any(l["id"] == label["id"] for l in updated["labels"])


def test_remove_label_not_assigned_returns_404(client, isolated_photos_dir):
    photo = _make_photo(client, isolated_photos_dir)
    label_id = client.get("/labels").json()[0]["id"]
    r = client.delete(f"/photos/{photo['id']}/labels/{label_id}")
    assert r.status_code == 404


def test_remove_label_bad_photo_returns_404(client):
    label_id = client.get("/labels").json()[0]["id"]
    r = client.delete(f"/photos/99999/labels/{label_id}")
    assert r.status_code == 404


# --- GET /photos includes labels ---

def test_get_photos_includes_labels_field(client, isolated_photos_dir):
    _make_photo(client, isolated_photos_dir)
    photo = client.get("/photos").json()[0]
    assert "labels" in photo
    assert isinstance(photo["labels"], list)


def test_get_photos_labels_empty_by_default(client, isolated_photos_dir):
    _make_photo(client, isolated_photos_dir)
    photo = client.get("/photos").json()[0]
    assert photo["labels"] == []


# --- POST /labels ---

def test_create_label_returns_201(client):
    r = client.post("/labels", json={"name": "rust"})
    assert r.status_code == 201


def test_create_label_returns_id_and_name(client):
    r = client.post("/labels", json={"name": "rust"})
    data = r.json()
    assert "id" in data
    assert data["name"] == "rust"


def test_create_label_normalizes_spaces_to_underscores(client):
    r = client.post("/labels", json={"name": "new symptoms"})
    assert r.json()["name"] == "new_symptoms"


def test_create_label_lowercases(client):
    r = client.post("/labels", json={"name": "Rust"})
    assert r.json()["name"] == "rust"


def test_create_label_trims_whitespace(client):
    r = client.post("/labels", json={"name": "  rust  "})
    assert r.json()["name"] == "rust"


def test_create_label_empty_returns_422(client):
    r = client.post("/labels", json={"name": ""})
    assert r.status_code == 422


def test_create_label_whitespace_only_returns_422(client):
    r = client.post("/labels", json={"name": "   "})
    assert r.status_code == 422


def test_create_label_existing_returns_existing_with_200(client):
    r1 = client.post("/labels", json={"name": "aphids"})
    r2 = client.post("/labels", json={"name": "aphids"})
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_create_label_existing_after_normalize_returns_existing(client):
    r1 = client.post("/labels", json={"name": "aphids"})
    r2 = client.post("/labels", json={"name": "  Aphids  "})
    assert r1.json()["id"] == r2.json()["id"]


def test_create_label_appears_in_get_labels(client):
    client.post("/labels", json={"name": "rust"})
    names = [l["name"] for l in client.get("/labels").json()]
    assert "rust" in names


# --- label uniqueness ---

def test_label_names_are_unique(client):
    labels = client.get("/labels").json()
    names = [l["name"] for l in labels]
    assert len(names) == len(set(names))
