"""Tests for GET /sensors/flower-care/latest and GET /sensors/flower-care/{mac}/readings."""
from datetime import datetime, timedelta, timezone

import pytest

INGEST_TOKEN = "test-ingest-token"
MAC_A = "5C:85:7E:14:43:45"
MAC_B = "AA:BB:CC:DD:EE:FF"


def _ts(offset_minutes: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def set_ingest_token(monkeypatch):
    monkeypatch.setenv("INGEST_API_TOKEN", INGEST_TOKEN)


def _ingest(client, rows):
    resp = client.post(
        "/sensors/ingest",
        json=rows,
        headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
    )
    assert resp.status_code == 200
    return resp.json()


def _row(mac=MAC_A, name="South bed", offset_minutes=0, **kwargs):
    base = {
        "mac": mac,
        "name": name,
        "recorded_at": _iso(_ts(offset_minutes)),
        "temperature_c": 21.5,
        "lux": 4200,
        "moisture_pct": 38,
        "conductivity_us_cm": 142,
    }
    base.update(kwargs)
    return base


class TestFlowerCareAuth:
    def test_ingest_bearer_accepted_on_latest(self, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        resp = client.get(
            "/sensors/flower-care/latest",
            headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_ingest_bearer_accepted_on_readings(self, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        resp = client.get(
            f"/sensors/flower-care/{MAC_A}/readings",
            headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_wrong_bearer_falls_through_to_session_auth(self, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        resp = client.get(
            "/sensors/flower-care/latest",
            headers={"Authorization": "Bearer wrongtoken"},
        )
        assert resp.status_code == 401

    def test_no_auth_falls_through_to_session_auth(self, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 401


class TestFlowerCareLatest:
    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_most_recent_per_mac(self, client):
        _ingest(client, [
            _row(offset_minutes=120),
            _row(offset_minutes=60),
            _row(offset_minutes=10),
        ])
        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mac"] == MAC_A
        # most recent row has smallest offset (10 min ago)
        assert data[0]["temperature_c"] == 21.5

    def test_one_row_per_mac(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=10),
            _row(mac=MAC_B, offset_minutes=20),
        ])
        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        macs = {r["mac"] for r in data}
        assert macs == {MAC_A, MAC_B}

    def test_fresh_reading_not_stale(self, client):
        _ingest(client, [_row(offset_minutes=89)])
        resp = client.get("/sensors/flower-care/latest")
        data = resp.json()
        assert data[0]["stale"] is False

    def test_old_reading_is_stale(self, client):
        _ingest(client, [_row(offset_minutes=91)])
        resp = client.get("/sensors/flower-care/latest")
        data = resp.json()
        assert data[0]["stale"] is True

    def test_stale_sensor_stays_in_list(self, client):
        _ingest(client, [_row(mac=MAC_A, offset_minutes=91)])
        resp = client.get("/sensors/flower-care/latest")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stale"] is True

    def test_response_includes_all_fields(self, client):
        _ingest(client, [_row(offset_minutes=5)])
        data = client.get("/sensors/flower-care/latest").json()
        r = data[0]
        assert "mac" in r
        assert "name" in r
        assert "recorded_at" in r
        assert "temperature_c" in r
        assert "lux" in r
        assert "moisture_pct" in r
        assert "conductivity_us_cm" in r
        assert "stale" in r


class TestFlowerCareReadings:
    def test_returns_readings_for_mac(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=120),
            _row(mac=MAC_A, offset_minutes=60),
        ])
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_unknown_mac_returns_empty(self, client):
        resp = client.get("/sensors/flower-care/FF:FF:FF:FF:FF:FF/readings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_does_not_return_other_mac(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=10),
            _row(mac=MAC_B, offset_minutes=10),
        ])
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings")
        data = resp.json()
        assert all(r["mac"] == MAC_A for r in data)
        assert len(data) == 1

    def test_ordered_by_recorded_at(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=120),
            _row(mac=MAC_A, offset_minutes=60),
            _row(mac=MAC_A, offset_minutes=10),
        ])
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings")
        data = resp.json()
        timestamps = [r["recorded_at"] for r in data]
        assert timestamps == sorted(timestamps)

    def test_start_ts_filters_older_rows(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=120),
            _row(mac=MAC_A, offset_minutes=30),
        ])
        cutoff = _iso(_ts(60))
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings?start_ts={cutoff}")
        data = resp.json()
        assert len(data) == 1

    def test_end_ts_filters_newer_rows(self, client):
        _ingest(client, [
            _row(mac=MAC_A, offset_minutes=10),
            _row(mac=MAC_A, offset_minutes=120),
        ])
        cutoff = _iso(_ts(60))
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings?end_ts={cutoff}")
        data = resp.json()
        assert len(data) == 1

    def test_naive_start_ts_returns_422(self, client):
        resp = client.get(
            f"/sensors/flower-care/{MAC_A}/readings?start_ts=2026-06-09T08:00:00"
        )
        assert resp.status_code == 422

    def test_naive_end_ts_returns_422(self, client):
        resp = client.get(
            f"/sensors/flower-care/{MAC_A}/readings?end_ts=2026-06-09T08:00:00"
        )
        assert resp.status_code == 422

    def test_response_has_no_stale_field(self, client):
        _ingest(client, [_row(offset_minutes=5)])
        data = client.get(f"/sensors/flower-care/{MAC_A}/readings").json()
        assert "stale" not in data[0]

    def test_max_points_without_timestamps_returns_422(self, client):
        resp = client.get(f"/sensors/flower-care/{MAC_A}/readings?max_points=5")
        assert resp.status_code == 422

    def test_max_points_zero_returns_422(self, client):
        start = _iso(_ts(120))
        end = _iso(_ts(0))
        resp = client.get(
            f"/sensors/flower-care/{MAC_A}/readings?start_ts={start}&end_ts={end}&max_points=0"
        )
        assert resp.status_code == 422

    def test_max_points_downsamples_spread_across_window(self, client):
        # 9 readings evenly spread: 10, 20, 30, 40, 50, 60, 70, 80, 90 minutes ago
        _ingest(client, [_row(mac=MAC_A, offset_minutes=i * 10) for i in range(1, 10)])
        start = _iso(_ts(95))
        end = _iso(_ts(5))
        resp = client.get(
            f"/sensors/flower-care/{MAC_A}/readings?start_ts={start}&end_ts={end}&max_points=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert 1 <= len(data) <= 3
        # Oldest returned reading must be from early in the window (not just the newest cluster).
        # With 3 buckets over ~90 min, the oldest bucket covers ~0-30 min from start_ts (~65-95
        # min ago). The newest bucket covers ~60-90 min from start_ts (~5-35 min ago).
        # So the spread between oldest and newest returned row must exceed 30 minutes.
        timestamps = sorted(data, key=lambda r: r["recorded_at"])
        oldest_dt = datetime.fromisoformat(timestamps[0]["recorded_at"])
        newest_dt = datetime.fromisoformat(timestamps[-1]["recorded_at"])
        assert (newest_dt - oldest_dt).total_seconds() > 30 * 60
