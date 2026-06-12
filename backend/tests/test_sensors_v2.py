"""Tests for /v2/sensors/meter/latest and /v2/sensors/flower-care/latest."""
from datetime import datetime, timedelta, timezone

import pytest

INGEST_TOKEN = "test-ingest-token"


def _headers():
    return {"Authorization": f"Bearer {INGEST_TOKEN}"}


def _sb_row(mac, ts, humidity_pct=65.0, temperature_c=21.5):
    return {
        "mac": mac,
        "name": mac,
        "recorded_at": ts,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "lux": None,
        "moisture_pct": None,
        "conductivity_us_cm": None,
    }


def _fc_row(mac, ts, temperature_c=21.5):
    return {
        "mac": mac,
        "name": mac,
        "recorded_at": ts,
        "temperature_c": temperature_c,
        "lux": 4200,
        "moisture_pct": 38,
        "conductivity_us_cm": 142,
    }


@pytest.fixture(autouse=True)
def set_ingest_token(monkeypatch):
    monkeypatch.setenv("INGEST_API_TOKEN", INGEST_TOKEN)


class TestMeterLatestV2:
    def test_response_has_sensors_and_retry_after(self, client):
        resp = client.get("/v2/sensors/meter/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "sensors" in data
        assert "retry_after_secs" in data

    def test_retry_after_is_positive(self, client):
        resp = client.get("/v2/sensors/meter/latest")
        assert resp.json()["retry_after_secs"] > 0

    def test_empty_sensors_when_no_data(self, client):
        resp = client.get("/v2/sensors/meter/latest")
        assert resp.json()["sensors"] == []

    def test_returns_meter_readings_only(self, client):
        fc = _fc_row("FC:00:00:00:00:01", "2026-06-09T08:00:00Z")
        sb = _sb_row("SB:00:00:00:00:01", "2026-06-09T08:00:00Z")
        client.post("/sensors/ingest", json=[fc, sb], headers=_headers())

        data = client.get("/v2/sensors/meter/latest").json()
        macs = [r["mac"] for r in data["sensors"]]
        assert "SB:00:00:00:00:01" in macs
        assert "FC:00:00:00:00:01" not in macs

    def test_returns_most_recent_per_mac(self, client):
        old = _sb_row("SB:AA:00:00:00:01", "2026-06-09T07:00:00Z", humidity_pct=60.0)
        new = _sb_row("SB:AA:00:00:00:01", "2026-06-09T08:00:00Z", humidity_pct=65.0)
        client.post("/sensors/ingest", json=[old, new], headers=_headers())

        data = client.get("/v2/sensors/meter/latest").json()
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["humidity_pct"] == pytest.approx(65.0)
        assert data["sensors"][0]["recorded_at"].startswith("2026-06-09T08:00:00")

    def test_one_row_per_mac(self, client):
        for ts in ("2026-06-09T06:00:00Z", "2026-06-09T07:00:00Z", "2026-06-09T08:00:00Z"):
            client.post("/sensors/ingest", json=[_sb_row("SB:BB:00:00:00:01", ts)], headers=_headers())

        data = client.get("/v2/sensors/meter/latest").json()
        assert len(data["sensors"]) == 1

    def test_stale_flag_true_when_old(self, client):
        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[_sb_row("SB:CC:00:00:00:01", stale_ts)], headers=_headers())

        data = client.get("/v2/sensors/meter/latest").json()
        assert data["sensors"][0]["stale"] is True

    def test_stale_flag_false_when_fresh(self, client):
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[_sb_row("SB:DD:00:00:00:01", fresh_ts)], headers=_headers())

        data = client.get("/v2/sensors/meter/latest").json()
        assert data["sensors"][0]["stale"] is False


class TestFlowerCareLatestV2:
    def test_response_has_sensors_and_retry_after(self, client):
        resp = client.get("/v2/sensors/flower-care/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "sensors" in data
        assert "retry_after_secs" in data

    def test_retry_after_is_positive(self, client):
        resp = client.get("/v2/sensors/flower-care/latest")
        assert resp.json()["retry_after_secs"] > 0

    def test_empty_sensors_when_no_data(self, client):
        resp = client.get("/v2/sensors/flower-care/latest")
        assert resp.json()["sensors"] == []

    def test_returns_flower_care_only(self, client):
        fc = _fc_row("FC:00:00:00:00:02", "2026-06-09T08:00:00Z")
        sb = _sb_row("SB:00:00:00:00:02", "2026-06-09T08:00:00Z")
        client.post("/sensors/ingest", json=[fc, sb], headers=_headers())

        data = client.get("/v2/sensors/flower-care/latest").json()
        macs = [r["mac"] for r in data["sensors"]]
        assert "FC:00:00:00:00:02" in macs
        assert "SB:00:00:00:00:02" not in macs

    def test_returns_most_recent_per_mac(self, client):
        old = _fc_row("FC:AA:00:00:00:01", "2026-06-09T07:00:00Z", temperature_c=20.0)
        new = _fc_row("FC:AA:00:00:00:01", "2026-06-09T08:00:00Z", temperature_c=22.0)
        client.post("/sensors/ingest", json=[old, new], headers=_headers())

        data = client.get("/v2/sensors/flower-care/latest").json()
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["temperature_c"] == pytest.approx(22.0)

    def test_stale_flag(self, client):
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[
            _fc_row("FC:BB:00:00:00:01", stale_ts),
            _fc_row("FC:CC:00:00:00:01", fresh_ts),
        ], headers=_headers())

        data = {r["mac"]: r for r in client.get("/v2/sensors/flower-care/latest").json()["sensors"]}
        assert data["FC:BB:00:00:00:01"]["stale"] is True
        assert data["FC:CC:00:00:00:01"]["stale"] is False


class TestSensorIdsV2:
    @pytest.fixture(autouse=True)
    def set_sensor_registry(self, monkeypatch):
        from app.sensor_registry import clear_sensor_registry_cache

        monkeypatch.setenv(
            "SWITCHBOT_SENSORS",
            '[{"id":"south","mac":"SB:ID:00:00:00:01","name":"South"}]',
        )
        monkeypatch.setenv(
            "XIAOMI_SENSORS",
            '[{"id":"cilantro","mac":"FC:ID:00:00:00:01","name":"Cilantro"}]',
        )
        clear_sensor_registry_cache()
        yield
        clear_sensor_registry_cache()

    def test_latest_includes_configured_meter_id(self, client):
        client.post(
            "/sensors/ingest",
            json=[_sb_row("SB:ID:00:00:00:01", "2026-06-09T08:00:00Z")],
            headers=_headers(),
        )

        data = client.get("/v2/sensors/meter/latest").json()

        assert data["sensors"][0]["id"] == "south"
        assert data["sensors"][0]["name"] == "South"
        assert data["sensors"][0]["type"] == "meter"

    def test_latest_includes_configured_flower_care_id(self, client):
        client.post(
            "/sensors/ingest",
            json=[_fc_row("FC:ID:00:00:00:01", "2026-06-09T08:00:00Z")],
            headers=_headers(),
        )

        data = client.get("/v2/sensors/flower-care/latest").json()

        assert data["sensors"][0]["id"] == "cilantro"
        assert data["sensors"][0]["name"] == "Cilantro"
        assert data["sensors"][0]["type"] == "flower-care"

    def test_readings_by_sensor_id_resolves_meter_mac(self, client):
        client.post(
            "/sensors/ingest",
            json=[_sb_row("SB:ID:00:00:00:01", "2026-06-09T08:00:00Z", humidity_pct=61.0)],
            headers=_headers(),
        )

        data = client.get(
            "/v2/sensors/south/readings",
            params={"start_ts": "2026-06-09T00:00:00Z", "end_ts": "2026-06-10T00:00:00Z"},
        ).json()

        assert len(data) == 1
        assert data[0]["mac"] == "SB:ID:00:00:00:01"
        assert data[0]["humidity_pct"] == pytest.approx(61.0)

    def test_readings_by_sensor_id_resolves_flower_care_mac(self, client):
        client.post(
            "/sensors/ingest",
            json=[_fc_row("FC:ID:00:00:00:01", "2026-06-09T08:00:00Z", temperature_c=23.0)],
            headers=_headers(),
        )

        data = client.get(
            "/v2/sensors/cilantro/readings",
            params={"start_ts": "2026-06-09T00:00:00Z", "end_ts": "2026-06-10T00:00:00Z"},
        ).json()

        assert len(data) == 1
        assert data[0]["mac"] == "FC:ID:00:00:00:01"
        assert data[0]["temperature_c"] == pytest.approx(23.0)

    def test_unknown_sensor_id_returns_404(self, client):
        resp = client.get("/v2/sensors/unknown/readings")
        assert resp.status_code == 404
