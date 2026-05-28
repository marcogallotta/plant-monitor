# --- POST /growing-units ---

def test_create_growing_unit_returns_201(client):
    r = client.post("/growing-units", json={"name": "Thai basil plant 1"})
    assert r.status_code == 201


def test_create_growing_unit_response_fields(client):
    r = client.post("/growing-units", json={
        "name": "Genovese basil plant 1",
        "unit_type": "individual",
        "species": "Ocimum basilicum",
        "variety": "Genovese",
    })
    data = r.json()
    assert data["name"] == "Genovese basil plant 1"
    assert data["unit_type"] == "individual"
    assert data["species"] == "Ocimum basilicum"
    assert data["variety"] == "Genovese"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_growing_unit_optional_fields_null(client):
    r = client.post("/growing-units", json={"name": "Chives clump"})
    data = r.json()
    assert data["unit_type"] is None
    assert data["species"] is None
    assert data["variety"] is None
    assert data["source"] is None
    assert data["started_at"] is None
    assert data["notes"] is None
    assert data["current_location_id"] is None


def test_create_growing_unit_name_required(client):
    r = client.post("/growing-units", json={"unit_type": "batch"})
    assert r.status_code == 422


def test_create_growing_unit_with_location(client):
    loc = client.post("/locations", json={"name": "Balcony"}).json()
    r = client.post("/growing-units", json={"name": "Mint pot", "current_location_id": loc["id"]})
    assert r.status_code == 201
    assert r.json()["current_location_id"] == loc["id"]


# --- GET /growing-units ---

def test_list_growing_units_empty(client):
    r = client.get("/growing-units")
    assert r.status_code == 200
    assert r.json() == []


def test_list_growing_units_returns_all(client):
    client.post("/growing-units", json={"name": "Thai basil plant 1"})
    client.post("/growing-units", json={"name": "French tarragon"})
    r = client.get("/growing-units")
    names = [u["name"] for u in r.json()]
    assert "Thai basil plant 1" in names
    assert "French tarragon" in names


# --- GET /growing-units/{id} ---

def test_get_growing_unit_returns_it(client):
    created = client.post("/growing-units", json={"name": "Lemongrass"}).json()
    r = client.get(f"/growing-units/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Lemongrass"


def test_get_growing_unit_unknown_returns_404(client):
    r = client.get("/growing-units/99999")
    assert r.status_code == 404


# --- PUT /growing-units/{id} ---

def test_update_growing_unit_name(client):
    created = client.post("/growing-units", json={"name": "Old name"}).json()
    r = client.put(f"/growing-units/{created['id']}", json={"name": "New name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New name"


def test_update_growing_unit_sets_type_and_notes(client):
    created = client.post("/growing-units", json={"name": "Chilli seedlings"}).json()
    r = client.put(f"/growing-units/{created['id']}", json={"unit_type": "batch", "notes": "Hangjiao H4"})
    assert r.status_code == 200
    data = r.json()
    assert data["unit_type"] == "batch"
    assert data["notes"] == "Hangjiao H4"


def test_update_growing_unit_location(client):
    loc = client.post("/locations", json={"name": "South rail"}).json()
    created = client.post("/growing-units", json={"name": "Mint pot"}).json()
    r = client.put(f"/growing-units/{created['id']}", json={"current_location_id": loc["id"]})
    assert r.status_code == 200
    assert r.json()["current_location_id"] == loc["id"]


def test_update_growing_unit_unknown_returns_404(client):
    r = client.put("/growing-units/99999", json={"name": "X"})
    assert r.status_code == 404


def test_create_growing_unit_bad_location_returns_404(client):
    r = client.post("/growing-units", json={"name": "Mint pot", "current_location_id": 99999})
    assert r.status_code == 404


def test_update_growing_unit_bad_location_returns_404(client):
    created = client.post("/growing-units", json={"name": "Mint pot"}).json()
    r = client.put(f"/growing-units/{created['id']}", json={"current_location_id": 99999})
    assert r.status_code == 404


def test_update_growing_unit_name_null_returns_422(client):
    r = client.post("/growing-units", json={"name": "Basil pot"})
    unit_id = r.json()["id"]
    assert client.put(f"/growing-units/{unit_id}", json={"name": None}).status_code == 422


def test_list_growing_units_ordered_by_name(client):
    client.post("/growing-units", json={"name": "Thai basil plant 1"})
    client.post("/growing-units", json={"name": "Chives clump"})
    names = [u["name"] for u in client.get("/growing-units").json()]
    assert names == sorted(names)
