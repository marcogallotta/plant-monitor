# --- POST /locations ---

def test_create_location_returns_201(client):
    r = client.post("/locations", json={"name": "Balcony"})
    assert r.status_code == 201


def test_create_location_response_fields(client):
    r = client.post("/locations", json={"name": "South rail", "description": "Sunny spot"})
    data = r.json()
    assert data["name"] == "South rail"
    assert data["description"] == "Sunny spot"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_location_description_optional(client):
    r = client.post("/locations", json={"name": "West windowsill"})
    assert r.status_code == 201
    assert r.json()["description"] is None


def test_create_location_name_required(client):
    r = client.post("/locations", json={})
    assert r.status_code == 422


# --- GET /locations ---

def test_list_locations_empty(client):
    r = client.get("/locations")
    assert r.status_code == 200
    assert r.json() == []


def test_list_locations_returns_all(client):
    client.post("/locations", json={"name": "Balcony"})
    client.post("/locations", json={"name": "South rail"})
    r = client.get("/locations")
    names = [l["name"] for l in r.json()]
    assert "Balcony" in names
    assert "South rail" in names


# --- GET /locations/{id} ---

def test_get_location_returns_it(client):
    created = client.post("/locations", json={"name": "Propagation area"}).json()
    r = client.get(f"/locations/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Propagation area"


def test_get_location_unknown_returns_404(client):
    r = client.get("/locations/99999")
    assert r.status_code == 404


# --- PUT /locations/{id} ---

def test_update_location_name(client):
    created = client.post("/locations", json={"name": "Old name"}).json()
    r = client.put(f"/locations/{created['id']}", json={"name": "New name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New name"


def test_update_location_description(client):
    created = client.post("/locations", json={"name": "Balcony"}).json()
    r = client.put(f"/locations/{created['id']}", json={"description": "Added later"})
    assert r.status_code == 200
    assert r.json()["description"] == "Added later"
    assert r.json()["name"] == "Balcony"


def test_update_location_unknown_returns_404(client):
    r = client.put("/locations/99999", json={"name": "X"})
    assert r.status_code == 404


def test_update_location_can_clear_description(client):
    created = client.post("/locations", json={"name": "Balcony", "description": "To be cleared"}).json()
    r = client.put(f"/locations/{created['id']}", json={"description": None})
    assert r.status_code == 200
    assert r.json()["description"] is None


def test_update_location_name_null_returns_422(client):
    r = client.post("/locations", json={"name": "Shelf"})
    loc_id = r.json()["id"]
    assert client.put(f"/locations/{loc_id}", json={"name": None}).status_code == 422


def test_list_locations_ordered_by_name(client):
    client.post("/locations", json={"name": "West windowsill"})
    client.post("/locations", json={"name": "Balcony"})
    names = [l["name"] for l in client.get("/locations").json()]
    assert names == sorted(names)
