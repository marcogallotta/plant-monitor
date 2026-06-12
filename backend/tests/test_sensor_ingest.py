"""Tests for the sensor ingest and read APIs."""
import os
from datetime import datetime, timedelta, timezone

import pytest


INGEST_TOKEN = "test-ingest-token"
BASE_TS = "2026-06-09T08:00:00Z"


def _headers():
    return {"Authorization": f"Bearer {INGEST_TOKEN}"}


def _row(**kwargs):
    base = {
        "mac": "5C:85:7E:14:43:45",
        "name": "South bed",
        "recorded_at": BASE_TS,
        "temperature_c": 21.5,
        "lux": 4200,
        "moisture_pct": 38,
        "conductivity_us_cm": 142,
    }
    base.update(kwargs)
    return base


def _meter_row(mac, ts, humidity_pct=65.0, temperature_c=21.5):
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


def _flower_care_row(mac, ts, temperature_c=21.5):
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


class TestIngestAuth:
    def test_requires_bearer_token(self, client):
        resp = client.post("/sensors/ingest", json=[_row()])
        assert resp.status_code == 401

    def test_rejects_wrong_token(self, client):
        resp = client.post("/sensors/ingest", json=[_row()],
                           headers={"Authorization": "Bearer wrongtoken"})
        assert resp.status_code == 401

    def test_accepts_correct_token(self, client):
        resp = client.post("/sensors/ingest", json=[_row()], headers=_headers())
        assert resp.status_code == 200


class TestIngestValidation:
    def test_rejects_naive_recorded_at(self, client):
        resp = client.post("/sensors/ingest",
                           json=[_row(recorded_at="2026-06-09T08:00:00")],
                           headers=_headers())
        assert resp.status_code == 422

    def test_accepts_offset_aware_recorded_at(self, client):
        resp = client.post("/sensors/ingest",
                           json=[_row(recorded_at="2026-06-09T10:00:00+02:00")],
                           headers=_headers())
        assert resp.status_code == 200

    def test_accepts_partial_reading(self, client):
        resp = client.post("/sensors/ingest",
                           json=[_row(temperature_c=None, lux=None)],
                           headers=_headers())
        assert resp.status_code == 200

    def test_empty_batch_returns_zeros(self, client):
        resp = client.post("/sensors/ingest", json=[], headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == {"inserted": 0, "skipped": 0}


class TestIngestUpsert:
    def test_inserts_new_rows(self, client):
        rows = [
            _row(recorded_at="2026-06-09T08:00:00Z"),
            _row(recorded_at="2026-06-09T09:00:00Z"),
        ]
        resp = client.post("/sensors/ingest", json=rows, headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 2
        assert data["skipped"] == 0

    def test_skips_duplicate_rows(self, client):
        row = _row()
        first = client.post("/sensors/ingest", json=[row], headers=_headers())
        assert first.json()["inserted"] == 1

        second = client.post("/sensors/ingest", json=[row], headers=_headers())
        assert second.status_code == 200
        assert second.json()["inserted"] == 0
        assert second.json()["skipped"] == 1

    def test_all_skipped_is_still_2xx(self, client):
        row = _row()
        client.post("/sensors/ingest", json=[row], headers=_headers())
        resp = client.post("/sensors/ingest", json=[row], headers=_headers())
        assert resp.status_code == 200

    def test_mixed_new_and_duplicate(self, client):
        row_a = _row(recorded_at="2026-06-09T08:00:00Z")
        row_b = _row(recorded_at="2026-06-09T09:00:00Z")
        client.post("/sensors/ingest", json=[row_a], headers=_headers())

        resp = client.post("/sensors/ingest", json=[row_a, row_b], headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 1
        assert data["skipped"] == 1

    def test_normalises_offset_to_utc(self, client):
        # +02:00 offset row is the same instant as Z row; second POST should be skipped
        row_plus2 = _row(recorded_at="2026-06-09T10:00:00+02:00")
        row_utc = _row(recorded_at="2026-06-09T08:00:00Z")
        client.post("/sensors/ingest", json=[row_plus2], headers=_headers())
        resp = client.post("/sensors/ingest", json=[row_utc], headers=_headers())
        assert resp.json()["skipped"] == 1

    def test_multiple_macs(self, client):
        rows = [
            _row(mac="AA:BB:CC:DD:EE:01", recorded_at="2026-06-09T08:00:00Z"),
            _row(mac="AA:BB:CC:DD:EE:02", recorded_at="2026-06-09T08:00:00Z"),
        ]
        resp = client.post("/sensors/ingest", json=rows, headers=_headers())
        assert resp.json()["inserted"] == 2

    def test_accepts_humidity_pct(self, client):
        row = _row(humidity_pct=65.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        resp = client.post("/sensors/ingest", json=[row], headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["inserted"] == 1


class TestSensorPhotoContext:
    def _sb_row(self, mac, ts):
        return _row(mac=mac, recorded_at=ts, humidity_pct=65.0,
                    lux=None, moisture_pct=None, conductivity_us_cm=None)

    def _make_photo(self, db_session, captured_at, suffix="0"):
        from app.models import Photo
        photo = Photo(
            filename=f"2026-01-01T{suffix}.jpg",
            storage_path=f"/tmp/ctx{suffix}.jpg",
            metadata_path=f"/tmp/ctx{suffix}.json",
            captured_at=captured_at,
            source="pi",
        )
        db_session.add(photo)
        db_session.commit()
        return photo

    def test_404_for_missing_photo(self, client):
        resp = client.get("/sensors/photos/99999")
        assert resp.status_code == 404

    def test_empty_when_no_readings_in_window(self, client, db_session):
        from datetime import datetime, timezone
        photo = self._make_photo(db_session, datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc), "A")
        resp = client.get(f"/sensors/photos/{photo.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["sensors"] == []

    def test_returns_readings_in_window(self, client, db_session):
        from datetime import datetime, timezone
        photo_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        photo = self._make_photo(db_session, photo_ts, "B")
        inside = self._sb_row("SB:01:00:00:00:01", "2026-01-01T11:30:00Z")
        assert client.post("/sensors/ingest", json=[inside], headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        data = resp.json()
        assert data["available"] is True
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["readings"][0]["temperature_c"] == pytest.approx(21.5)

    def test_excludes_readings_outside_window(self, client, db_session):
        from datetime import datetime, timezone
        photo_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        photo = self._make_photo(db_session, photo_ts, "C")
        outside = self._sb_row("SB:01:00:00:00:02", "2026-01-01T10:59:00Z")  # >61 min before
        assert client.post("/sensors/ingest", json=[outside], headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        data = resp.json()
        assert data["sensors"] == []

    def test_excludes_flower_care_rows(self, client, db_session):
        from datetime import datetime, timezone
        photo_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        photo = self._make_photo(db_session, photo_ts, "D")
        fc = _row(mac="FC:01:00:00:00:01", recorded_at="2026-01-01T12:00:00Z")
        assert client.post("/sensors/ingest", json=[fc], headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        assert resp.json()["sensors"] == []

    def test_groups_by_sensor(self, client, db_session):
        from datetime import datetime, timezone
        photo_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        photo = self._make_photo(db_session, photo_ts, "E")
        rows = [
            self._sb_row("SB:01:00:00:00:03", "2026-01-01T11:30:00Z"),
            self._sb_row("SB:01:00:00:00:04", "2026-01-01T12:00:00Z"),
        ]
        assert client.post("/sensors/ingest", json=rows, headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        data = resp.json()
        assert data["available"] is True
        assert len(data["sensors"]) == 2

    def test_naive_captured_at_treated_as_utc(self, client, db_session):
        from datetime import datetime
        photo = self._make_photo(db_session, datetime(2026, 1, 1, 12, 0, 0), "F")
        inside = self._sb_row("SB:01:00:00:00:05", "2026-01-01T12:00:00Z")
        assert client.post("/sensors/ingest", json=[inside], headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        assert resp.json()["available"] is True

    def test_renamed_sensor_produces_one_group_not_two(self, client, db_session):
        from datetime import datetime, timezone
        photo_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        photo = self._make_photo(db_session, photo_ts, "G")
        old_name = _row(mac="SB:01:00:00:00:06", name="Old Name",
                        recorded_at="2026-01-01T11:30:00Z", humidity_pct=60.0,
                        lux=None, moisture_pct=None, conductivity_us_cm=None)
        new_name = _row(mac="SB:01:00:00:00:06", name="New Name",
                        recorded_at="2026-01-01T12:00:00Z", humidity_pct=62.0,
                        lux=None, moisture_pct=None, conductivity_us_cm=None)
        assert client.post("/sensors/ingest", json=[old_name, new_name], headers=_headers()).status_code == 200

        resp = client.get(f"/sensors/photos/{photo.id}")
        data = resp.json()
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["name"] == "New Name"
        assert len(data["sensors"][0]["readings"]) == 2
        assert len(resp.json()["sensors"]) == 1


class TestMeterLatest:
    def test_response_has_sensors_and_retry_after(self, client):
        resp = client.get("/sensors/meter/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "sensors" in data
        assert "retry_after_secs" in data

    def test_retry_after_is_positive(self, client):
        resp = client.get("/sensors/meter/latest")
        assert resp.json()["retry_after_secs"] > 0

    def test_empty_sensors_when_no_data(self, client):
        resp = client.get("/sensors/meter/latest")
        assert resp.json()["sensors"] == []

    def test_returns_meter_readings_only(self, client):
        fc = _flower_care_row("FC:00:00:00:00:01", "2026-06-09T08:00:00Z")
        meter = _meter_row("SB:00:00:00:00:01", "2026-06-09T08:00:00Z")
        client.post("/sensors/ingest", json=[fc, meter], headers=_headers())

        data = client.get("/sensors/meter/latest").json()
        macs = [r["mac"] for r in data["sensors"]]
        assert "SB:00:00:00:00:01" in macs
        assert "FC:00:00:00:00:01" not in macs

    def test_returns_most_recent_per_mac(self, client):
        old = _meter_row("SB:AA:00:00:00:01", "2026-06-09T07:00:00Z", humidity_pct=60.0)
        new = _meter_row("SB:AA:00:00:00:01", "2026-06-09T08:00:00Z", humidity_pct=65.0)
        client.post("/sensors/ingest", json=[old, new], headers=_headers())

        data = client.get("/sensors/meter/latest").json()
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["humidity_pct"] == pytest.approx(65.0)
        assert data["sensors"][0]["recorded_at"].startswith("2026-06-09T08:00:00")

    def test_one_row_per_mac(self, client):
        for ts in ("2026-06-09T06:00:00Z", "2026-06-09T07:00:00Z", "2026-06-09T08:00:00Z"):
            client.post("/sensors/ingest", json=[_meter_row("SB:BB:00:00:00:01", ts)], headers=_headers())

        data = client.get("/sensors/meter/latest").json()
        assert len(data["sensors"]) == 1

    def test_stale_flag_true_when_old(self, client):
        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[_meter_row("SB:CC:00:00:00:01", stale_ts)], headers=_headers())

        data = client.get("/sensors/meter/latest").json()
        assert data["sensors"][0]["stale"] is True

    def test_stale_flag_false_when_fresh(self, client):
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[_meter_row("SB:DD:00:00:00:01", fresh_ts)], headers=_headers())

        data = client.get("/sensors/meter/latest").json()
        assert data["sensors"][0]["stale"] is False


class TestFlowerCareLatest:
    def test_response_has_sensors_and_retry_after(self, client):
        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "sensors" in data
        assert "retry_after_secs" in data

    def test_retry_after_is_positive(self, client):
        resp = client.get("/sensors/flower-care/latest")
        assert resp.json()["retry_after_secs"] > 0

    def test_empty_sensors_when_no_data(self, client):
        resp = client.get("/sensors/flower-care/latest")
        assert resp.json()["sensors"] == []

    def test_returns_flower_care_only(self, client):
        fc = _flower_care_row("FC:00:00:00:00:02", "2026-06-09T08:00:00Z")
        meter = _meter_row("SB:00:00:00:00:02", "2026-06-09T08:00:00Z")
        client.post("/sensors/ingest", json=[fc, meter], headers=_headers())

        data = client.get("/sensors/flower-care/latest").json()
        macs = [r["mac"] for r in data["sensors"]]
        assert "FC:00:00:00:00:02" in macs
        assert "SB:00:00:00:00:02" not in macs

    def test_returns_most_recent_per_mac(self, client):
        old = _flower_care_row("FC:AA:00:00:00:01", "2026-06-09T07:00:00Z", temperature_c=20.0)
        new = _flower_care_row("FC:AA:00:00:00:01", "2026-06-09T08:00:00Z", temperature_c=22.0)
        client.post("/sensors/ingest", json=[old, new], headers=_headers())

        data = client.get("/sensors/flower-care/latest").json()
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["temperature_c"] == pytest.approx(22.0)

    def test_stale_flag(self, client):
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        client.post("/sensors/ingest", json=[
            _flower_care_row("FC:BB:00:00:00:01", stale_ts),
            _flower_care_row("FC:CC:00:00:00:01", fresh_ts),
        ], headers=_headers())

        data = {r["mac"]: r for r in client.get("/sensors/flower-care/latest").json()["sensors"]}
        assert data["FC:BB:00:00:00:01"]["stale"] is True
        assert data["FC:CC:00:00:00:01"]["stale"] is False


class TestSensorIds:
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
            json=[_meter_row("SB:ID:00:00:00:01", "2026-06-09T08:00:00Z")],
            headers=_headers(),
        )

        data = client.get("/sensors/meter/latest").json()

        assert data["sensors"][0]["id"] == "south"
        assert data["sensors"][0]["name"] == "South"
        assert data["sensors"][0]["type"] == "meter"

    def test_latest_includes_configured_flower_care_id(self, client):
        client.post(
            "/sensors/ingest",
            json=[_flower_care_row("FC:ID:00:00:00:01", "2026-06-09T08:00:00Z")],
            headers=_headers(),
        )

        data = client.get("/sensors/flower-care/latest").json()

        assert data["sensors"][0]["id"] == "cilantro"
        assert data["sensors"][0]["name"] == "Cilantro"
        assert data["sensors"][0]["type"] == "flower-care"

    def test_readings_by_sensor_id_resolves_meter_mac(self, client):
        client.post(
            "/sensors/ingest",
            json=[_meter_row("SB:ID:00:00:00:01", "2026-06-09T08:00:00Z", humidity_pct=61.0)],
            headers=_headers(),
        )

        data = client.get(
            "/sensors/south/readings",
            params={"start_ts": "2026-06-09T00:00:00Z", "end_ts": "2026-06-10T00:00:00Z"},
        ).json()

        assert len(data) == 1
        assert data[0]["mac"] == "SB:ID:00:00:00:01"
        assert data[0]["humidity_pct"] == pytest.approx(61.0)

    def test_readings_by_sensor_id_resolves_flower_care_mac(self, client):
        client.post(
            "/sensors/ingest",
            json=[_flower_care_row("FC:ID:00:00:00:01", "2026-06-09T08:00:00Z", temperature_c=23.0)],
            headers=_headers(),
        )

        data = client.get(
            "/sensors/cilantro/readings",
            params={"start_ts": "2026-06-09T00:00:00Z", "end_ts": "2026-06-10T00:00:00Z"},
        ).json()

        assert len(data) == 1
        assert data[0]["mac"] == "FC:ID:00:00:00:01"
        assert data[0]["temperature_c"] == pytest.approx(23.0)

    def test_unknown_sensor_id_returns_404(self, client):
        resp = client.get("/sensors/unknown/readings")
        assert resp.status_code == 404
