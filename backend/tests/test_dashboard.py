def test_dashboard_returns_200(client):
    assert client.get("/").status_code == 200


def test_dashboard_returns_html(client):
    resp = client.get("/")
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_contains_photos_api_call(client):
    resp = client.get("/")
    assert b"/photos" in resp.content


def test_dashboard_contains_filter_inputs(client):
    resp = client.get("/")
    assert b"datetime-local" in resp.content


def test_dashboard_has_comparison_view(client):
    resp = client.get("/")
    assert b"compare" in resp.content.lower()


def test_dashboard_has_flicker_control(client):
    resp = client.get("/")
    assert b"flicker" in resp.content.lower()


def test_dashboard_has_timelapse_controls(client):
    resp = client.get("/")
    assert b"timelapse" in resp.content.lower()
    assert b"play" in resp.content.lower()
    assert b"prev" in resp.content.lower() or b"previous" in resp.content.lower()


def test_dashboard_has_notes_ui(client):
    resp = client.get("/")
    assert b"note" in resp.content.lower()


def test_dashboard_has_manual_upload_form(client):
    resp = client.get("/")
    assert b"manual-photos" in resp.content


def test_dashboard_has_source_filter(client):
    resp = client.get("/")
    assert b"source" in resp.content.lower()


def test_dashboard_has_photo_type_filter(client):
    resp = client.get("/")
    assert b"photo_type" in resp.content or b"photo-type" in resp.content


def test_dashboard_has_location_filter(client):
    resp = client.get("/")
    assert b"/locations" in resp.content


def test_dashboard_has_growing_unit_filter(client):
    resp = client.get("/")
    assert b"/growing-units" in resp.content


def test_dashboard_has_identity_panel(client):
    resp = client.get("/")
    assert b"identity" in resp.content.lower() or b"growing_units" in resp.content or b"source" in resp.content.lower()
