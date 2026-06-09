"""Session-cookie auth for the dashboard (replaces HTTP Basic)."""


def test_no_password_set_allows_access(client, monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    resp = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 200


def test_browser_redirected_to_login(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_api_request_gets_401_not_redirect(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    # No text/html in Accept -> JSON 401, and crucially no WWW-Authenticate
    # header (that is what triggers the browser's native password popup).
    resp = client.get("/", headers={"Accept": "application/json"}, follow_redirects=False)
    assert resp.status_code == 401
    assert "www-authenticate" not in {k.lower() for k in resp.headers}


def test_login_page_reachable_unauthenticated(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


def test_wrong_password_rejected(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "error=1" in resp.headers["location"]
    # Still not authenticated.
    after = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert after.status_code == 303


def test_correct_password_grants_session(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.post(
        "/login",
        data={"password": "secret", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    # The session cookie now grants access without a prompt.
    after = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert after.status_code == 200


def test_open_redirect_blocked(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.post(
        "/login",
        data={"password": "secret", "next": "//evil.example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_session_grants_api_access(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    # An auth-required API endpoint is blocked without a session...
    assert client.get("/photos", follow_redirects=False).status_code == 401
    client.post("/login", data={"password": "secret"}, follow_redirects=False)
    # ...and reachable once the session cookie is set.
    assert client.get("/photos", follow_redirects=False).status_code == 200


def test_logout_clears_session(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert client.get("/", headers={"Accept": "text/html"}, follow_redirects=False).status_code == 200
    # GET must not log out (blocks CSRF via <img src=/logout>); only POST does.
    client.get("/logout", follow_redirects=False)
    assert client.get("/", headers={"Accept": "text/html"}, follow_redirects=False).status_code == 200
    client.post("/logout", follow_redirects=False)
    assert client.get("/", headers={"Accept": "text/html"}, follow_redirects=False).status_code == 303


# --- INGEST_API_TOKEN bearer auth ---

def test_ingest_token_accepted_on_post_photos(client, monkeypatch, isolated_photos_dir):
    import json
    monkeypatch.setenv("INGEST_API_TOKEN", "pi-secret")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    stem = "2026-05-26T103000Z"
    meta = {"captured_at": "2026-05-26T10:30:00Z", "filename": f"{stem}.jpg"}
    resp = client.post(
        "/photos",
        files={
            "image": (f"{stem}.jpg", b"FAKEJPEG", "image/jpeg"),
            "metadata": (f"{stem}.json", json.dumps(meta).encode(), "application/json"),
        },
        headers={"Authorization": "Bearer pi-secret"},
        follow_redirects=False,
    )
    assert resp.status_code not in (401, 403)


def test_ingest_token_rejected_with_wrong_value(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_TOKEN", "pi-secret")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.post(
        "/photos",
        files={"image": ("x.jpg", b"", "image/jpeg")},
        headers={"Authorization": "Bearer wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_ingest_token_does_not_grant_access_to_other_routes(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_TOKEN", "pi-secret")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    resp = client.get(
        "/photos",
        headers={"Authorization": "Bearer pi-secret"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
