def test_dashboard_returns_200(client):
    assert client.get("/").status_code == 200


def test_dashboard_returns_html(client):
    resp = client.get("/")
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_loads_app_js(client):
    resp = client.get("/")
    assert b"/static/app.js" in resp.content


def test_app_js_returns_200(client):
    assert client.get("/static/app.js").status_code == 200


def test_app_js_contains_photos_api_call(client):
    resp = client.get("/static/api.js")
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
    resp = client.get("/static/api.js")
    assert b"manual-photos" in resp.content


def test_dashboard_has_source_filter(client):
    resp = client.get("/")
    assert b"source" in resp.content.lower()


def test_dashboard_has_photo_type_filter(client):
    resp = client.get("/")
    assert b"photo_type" in resp.content or b"photo-type" in resp.content


def test_dashboard_has_location_filter(client):
    resp = client.get("/static/api.js")
    assert b"/locations" in resp.content


def test_dashboard_has_growing_unit_filter(client):
    resp = client.get("/static/api.js")
    assert b"/growing-units" in resp.content


def test_dashboard_has_identity_panel(client):
    resp = client.get("/")
    assert b"identity" in resp.content.lower() or b"growing_units" in resp.content or b"source" in resp.content.lower()


def test_dashboard_has_manage_panel(client):
    resp = client.get("/")
    assert b"manage" in resp.content.lower()


def test_dashboard_has_add_location_form(client):
    resp = client.get("/")
    assert b"new-loc-name" in resp.content
    assert b"Add location" in resp.content


def test_dashboard_has_add_unit_form(client):
    resp = client.get("/")
    assert b"new-unit-name" in resp.content
    assert b"Add unit" in resp.content


def test_dashboard_has_events_ui(client):
    assert b"/events" in client.get("/static/api.js").content
    assert b"Log event" in client.get("/static/index.html").content
