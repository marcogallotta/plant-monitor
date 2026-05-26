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
