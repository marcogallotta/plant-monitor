from datetime import datetime
import app.main
from app.models import Photo, PhotoGrowingUnit, PhotoLabel


def _photo(db_session, stem, captured_at_str, **kwargs):
    captured_at = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
    photos_dir = app.main.PHOTOS_DIR
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(photos_dir / f"{stem}.jpg"),
        metadata_path=str(photos_dir / f"{stem}.json"),
        **kwargs,
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def _link(db_session, photo_id, unit_id):
    db_session.add(PhotoGrowingUnit(photo_id=photo_id, growing_unit_id=unit_id))
    db_session.commit()


# --- GET /photos richer response ---

def test_list_photos_includes_source(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", source="pi")
    data = client.get("/photos").json()
    assert data["photos"][0]["source"] == "pi"


def test_list_photos_includes_photo_type(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", photo_type="overview")
    data = client.get("/photos").json()
    assert data["photos"][0]["photo_type"] == "overview"


def test_list_photos_includes_original_filename(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", original_filename="IMG_001.jpg")
    data = client.get("/photos").json()
    assert data["photos"][0]["original_filename"] == "IMG_001.jpg"


def test_list_photos_includes_location(client, db_session):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", location_id=loc["id"])
    data = client.get("/photos").json()
    assert data["photos"][0]["location_id"] == loc["id"]
    assert data["photos"][0]["location_name"] == "Balcony"


def test_list_photos_includes_growing_units(client, db_session):
    unit = client.post("/growing-units", json={"name": "Thai basil plant 1", "unit_type": "individual"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _link(db_session, photo.id, unit["id"])
    data = client.get("/photos").json()
    assert len(data["photos"][0]["growing_units"]) == 1
    assert data["photos"][0]["growing_units"][0]["id"] == unit["id"]
    assert data["photos"][0]["growing_units"][0]["name"] == "Thai basil plant 1"
    assert data["photos"][0]["growing_units"][0]["unit_type"] == "individual"


def test_list_photos_growing_units_empty_list(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    data = client.get("/photos").json()
    assert data["photos"][0]["growing_units"] == []


# --- GET /photos filters ---

def test_filter_by_source(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", source="pi")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z", source="manual")
    data = client.get("/photos?source=pi").json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["source"] == "pi"


def test_filter_by_photo_type(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", photo_type="overview")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z", photo_type="closeup")
    data = client.get("/photos?photo_type=overview").json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["photo_type"] == "overview"


def test_filter_by_location_id(client, db_session):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", location_id=loc["id"])
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    data = client.get(f"/photos?location_id={loc['id']}").json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["location_id"] == loc["id"]


def test_filter_by_growing_unit_id(client, db_session):
    unit = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    p1 = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    _link(db_session, p1.id, unit["id"])
    data = client.get(f"/photos?growing_unit_id={unit['id']}").json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["id"] == p1.id


def test_filter_by_label_id(client, db_session):
    label = client.post("/labels", json={"name": "new_growth"}).json()
    p1 = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    db_session.add(PhotoLabel(photo_id=p1.id, label_id=label["id"]))
    db_session.commit()
    data = client.get(f"/photos?label_id={label['id']}").json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["id"] == p1.id


def test_filter_by_label_id_no_match(client, db_session):
    label = client.post("/labels", json={"name": "new_growth"}).json()
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    data = client.get(f"/photos?label_id={label['id']}").json()
    assert data["photos"] == []


def test_filter_unclassified_still_shows_without_filters(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    data = client.get("/photos").json()
    assert len(data["photos"]) == 1


# --- pagination ---

def test_list_photos_limit_zero_returns_422(client):
    assert client.get("/photos?limit=0").status_code == 422


def test_list_photos_limit_above_max_returns_422(client):
    assert client.get("/photos?limit=501").status_code == 422


def test_list_photos_negative_offset_returns_422(client):
    assert client.get("/photos?offset=-1").status_code == 422


def test_list_photos_total_reflects_full_count(client, db_session):
    for i in range(3):
        _photo(db_session, f"2026-05-26T1{i}0000Z", f"2026-05-26T1{i}:00:00Z")
    data = client.get("/photos?limit=2").json()
    assert data["total"] == 3
    assert len(data["photos"]) == 2


def test_list_photos_offset_returns_correct_slice(client, db_session):
    for i in range(3):
        _photo(db_session, f"2026-05-26T1{i}0000Z", f"2026-05-26T1{i}:00:00Z")
    data = client.get("/photos?limit=2&offset=2").json()
    assert data["total"] == 3
    assert len(data["photos"]) == 1


def test_filter_by_source_total_reflects_filtered_count(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", source="pi")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z", source="manual")
    data = client.get("/photos?source=pi").json()
    assert data["total"] == 1
    assert len(data["photos"]) == 1


def test_filter_by_label_id_total_reflects_filtered_count(client, db_session):
    label = client.post("/labels", json={"name": "new_growth"}).json()
    p1 = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    db_session.add(PhotoLabel(photo_id=p1.id, label_id=label["id"]))
    db_session.commit()
    data = client.get(f"/photos?label_id={label['id']}").json()
    assert data["total"] == 1
    assert len(data["photos"]) == 1


def test_filter_by_growing_unit_id_total_reflects_filtered_count(client, db_session):
    unit = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    p1 = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    _photo(db_session, "2026-05-26T110000Z", "2026-05-26T11:00:00Z")
    _link(db_session, p1.id, unit["id"])
    data = client.get(f"/photos?growing_unit_id={unit['id']}").json()
    assert data["total"] == 1
    assert len(data["photos"]) == 1


def test_same_timestamp_pagination_stable_ordering(client, db_session):
    # All three photos share the same captured_at; secondary sort by id must keep pagination stable
    ts = "2026-05-26T10:00:00Z"
    p1 = _photo(db_session, "2026-05-26T100000Z_a", ts)
    p2 = _photo(db_session, "2026-05-26T100000Z_b", ts)
    p3 = _photo(db_session, "2026-05-26T100000Z_c", ts)
    page1 = client.get("/photos?limit=2&offset=0").json()
    page2 = client.get("/photos?limit=2&offset=2").json()
    assert page1["total"] == 3
    assert page2["total"] == 3
    ids_page1 = {p["id"] for p in page1["photos"]}
    ids_page2 = {p["id"] for p in page2["photos"]}
    assert ids_page1.isdisjoint(ids_page2)
    assert ids_page1 | ids_page2 == {p1.id, p2.id, p3.id}


# --- PUT /photos/{id} classification ---

def test_classify_photo_type(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"photo_type": "closeup"})
    assert r.status_code == 200
    assert r.json()["photo_type"] == "closeup"


def test_classify_photo_location(client, db_session):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"location_id": loc["id"]})
    assert r.status_code == 200
    assert r.json()["location_id"] == loc["id"]


def test_classify_photo_bad_location_returns_404(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"location_id": 99999})
    assert r.status_code == 404


def test_classify_photo_links_growing_units(client, db_session):
    u1 = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    u2 = client.post("/growing-units", json={"name": "Genovese basil plant 1"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"growing_unit_ids": [u1["id"], u2["id"]]})
    assert r.status_code == 200
    unit_ids = {u["id"] for u in r.json()["growing_units"]}
    assert unit_ids == {u1["id"], u2["id"]}


def test_classify_photo_replaces_growing_units(client, db_session):
    u1 = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    u2 = client.post("/growing-units", json={"name": "Genovese basil plant 1"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    client.put(f"/photos/{photo.id}", json={"growing_unit_ids": [u1["id"]]})
    r = client.put(f"/photos/{photo.id}", json={"growing_unit_ids": [u2["id"]]})
    unit_ids = {u["id"] for u in r.json()["growing_units"]}
    assert unit_ids == {u2["id"]}


def test_classify_photo_bad_growing_unit_returns_404(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"growing_unit_ids": [99999]})
    assert r.status_code == 404


def test_classify_photo_unknown_returns_404(client, db_session):
    r = client.put("/photos/99999", json={"photo_type": "closeup"})
    assert r.status_code == 404


def test_classify_photo_can_clear_photo_type(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", photo_type="closeup")
    r = client.put(f"/photos/{photo.id}", json={"photo_type": None})
    assert r.status_code == 200
    assert r.json()["photo_type"] is None


def test_classify_photo_can_clear_location(client, db_session):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", location_id=loc["id"])
    r = client.put(f"/photos/{photo.id}", json={"location_id": None})
    assert r.status_code == 200
    assert r.json()["location_id"] is None


def test_classify_photo_rotation(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    assert photo.rotation == 0
    r = client.put(f"/photos/{photo.id}", json={"rotation": 90})
    assert r.status_code == 200
    assert r.json()["rotation"] == 90
    r = client.put(f"/photos/{photo.id}", json={"rotation": 270})
    assert r.json()["rotation"] == 270


def test_classify_photo_rotation_invalid_returns_422(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"rotation": 45})
    assert r.status_code == 422


def test_classify_photo_rotation_null_returns_422(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    r = client.put(f"/photos/{photo.id}", json={"rotation": None})
    assert r.status_code == 422


def test_list_photos_includes_rotation(client, db_session):
    _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", rotation=180)
    data = client.get("/photos").json()
    assert data["photos"][0]["rotation"] == 180


# --- Pi upload sets source='pi' ---

def test_classify_photo_clears_growing_units_with_empty_list(client, db_session):
    u1 = client.post("/growing-units", json={"name": "Thai basil plant 1"}).json()
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z")
    client.put(f"/photos/{photo.id}", json={"growing_unit_ids": [u1["id"]]})
    r = client.put(f"/photos/{photo.id}", json={"growing_unit_ids": []})
    assert r.status_code == 200
    assert r.json()["growing_units"] == []


def test_classify_only_rotation_does_not_clear_photo_type(client, db_session):
    photo = _photo(db_session, "2026-05-26T100000Z", "2026-05-26T10:00:00Z", photo_type="overview")
    r = client.put(f"/photos/{photo.id}", json={"rotation": 90})
    assert r.status_code == 200
    assert r.json()["photo_type"] == "overview"


def test_pi_upload_sets_source_pi(client, isolated_photos_dir):
    import json as _json
    stem = "2026-05-26T100000Z"
    image_bytes = b"FAKEIMAGE"
    meta_bytes = _json.dumps({
        "captured_at": "2026-05-26T10:00:00Z",
        "filename": f"{stem}.jpg",
    }).encode()
    client.post("/photos", files={
        "image": (f"{stem}.jpg", image_bytes, "image/jpeg"),
        "metadata": (f"{stem}.json", meta_bytes, "application/json"),
    })
    data = client.get("/photos").json()
    assert data["photos"][0]["source"] == "pi"


# --- stabilization transform (tilt/drift correction) ---

def test_list_photos_includes_stabilization(client, db_session):
    photo = _photo(
        db_session, "2026-06-07T130010Z", "2026-06-07T13:00:10Z", source="pi",
        stab_matrix=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        stab_ref_w=1600, stab_ref_h=900, stab_status="anchor",
    )
    p = client.get("/photos").json()["photos"][0]
    assert p["stab_matrix"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert p["stab_ref_w"] == 1600 and p["stab_ref_h"] == 900
    assert p["stab_status"] == "anchor"


def test_list_photos_stabilization_null_by_default(client, db_session):
    _photo(db_session, "2026-06-07T130010Z", "2026-06-07T13:00:10Z", source="phone")
    p = client.get("/photos").json()["photos"][0]
    assert p["stab_matrix"] is None
    assert p["stab_ref_w"] is None
    assert p["stab_status"] is None
