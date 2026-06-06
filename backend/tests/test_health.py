from datetime import datetime, timedelta, timezone

import app.main
from app.models import Photo


def _pi_photo(db_session, captured_at, source="pi"):
    stem = captured_at.strftime("%Y-%m-%dT%H%M%SZ")
    photos_dir = app.main.PHOTOS_DIR
    photo = Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(photos_dir / f"{stem}.jpg"),
        metadata_path=str(photos_dir / f"{stem}.json"),
        source=source,
    )
    db_session.add(photo)
    db_session.commit()
    return photo


def test_liveness_always_ok(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_fresh_capture_is_ok(client, db_session):
    _pi_photo(db_session, datetime.now(timezone.utc) - timedelta(minutes=10))
    resp = client.get("/health/captures")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["age_minutes"] <= 11
    assert body["threshold_minutes"] == 90


def test_stale_capture_returns_503(client, db_session):
    _pi_photo(db_session, datetime.now(timezone.utc) - timedelta(minutes=200))
    resp = client.get("/health/captures")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "stale"
    assert body["age_minutes"] >= 199


def test_no_pi_photos_is_stale(client, db_session):
    resp = client.get("/health/captures")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "stale"
    assert body["last_capture_at"] is None
    assert body["age_minutes"] is None


def test_ignores_non_pi_sources(client, db_session):
    # A fresh manual upload must not mask a dead Pi.
    _pi_photo(db_session, datetime.now(timezone.utc) - timedelta(minutes=5), source="manual")
    _pi_photo(db_session, datetime.now(timezone.utc) - timedelta(minutes=200), source="pi")
    resp = client.get("/health/captures")
    assert resp.status_code == 503
    assert resp.json()["status"] == "stale"


def test_health_skips_auth(client, db_session, monkeypatch):
    # Reachable without the dashboard password so external monitors can poll it.
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    _pi_photo(db_session, datetime.now(timezone.utc) - timedelta(minutes=10))
    resp = client.get("/health/captures")
    assert resp.status_code == 200
