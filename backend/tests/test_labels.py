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
    assert "watered" in names
    assert "fed_liquid" in names
    assert "harvested" in names


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


# --- label uniqueness ---

def test_label_names_are_unique(client):
    labels = client.get("/labels").json()
    names = [l["name"] for l in labels]
    assert len(names) == len(set(names))
