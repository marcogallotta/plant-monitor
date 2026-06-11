"""Tests for POST /sensors/ingest."""
import os
from datetime import datetime, timezone

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


class TestFlowerCareLatest:
    def test_excludes_meter_rows(self, client):
        fc_row = _row(mac="FC:00:00:00:00:01", recorded_at="2026-06-09T08:00:00Z")
        sb_row = _row(mac="SB:00:00:00:00:01", recorded_at="2026-06-09T08:00:00Z",
                      humidity_pct=65.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        assert client.post("/sensors/ingest", json=[fc_row, sb_row], headers=_headers()).status_code == 200

        resp = client.get("/sensors/flower-care/latest")
        assert resp.status_code == 200
        macs = [r["mac"] for r in resp.json()]
        assert "FC:00:00:00:00:01" in macs
        assert "SB:00:00:00:00:01" not in macs


class TestMeterLatest:
    def test_empty_when_no_meter_readings(self, client):
        resp = client.get("/sensors/meter/latest")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_meter_readings_only(self, client):
        # Flower Care row (no humidity_pct)
        fc_row = _row(mac="FC:00:00:00:00:01", recorded_at="2026-06-09T08:00:00Z")
        assert client.post("/sensors/ingest", json=[fc_row], headers=_headers()).status_code == 200
        # SwitchBot meter row (has humidity_pct)
        sb_row = _row(mac="SB:00:00:00:00:01", recorded_at="2026-06-09T08:00:00Z",
                      humidity_pct=65.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        assert client.post("/sensors/ingest", json=[sb_row], headers=_headers()).status_code == 200

        resp = client.get("/sensors/meter/latest")
        assert resp.status_code == 200
        data = resp.json()
        macs = [r["mac"] for r in data]
        assert "SB:00:00:00:00:01" in macs
        assert "FC:00:00:00:00:01" not in macs

    def test_returns_most_recent_per_mac(self, client):
        old = _row(mac="SB:00:00:00:00:01", recorded_at="2026-06-09T07:00:00Z",
                   humidity_pct=60.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        new = _row(mac="SB:00:00:00:00:01", recorded_at="2026-06-09T08:00:00Z",
                   humidity_pct=65.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        assert client.post("/sensors/ingest", json=[old, new], headers=_headers()).status_code == 200

        resp = client.get("/sensors/meter/latest")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["humidity_pct"] == pytest.approx(65.0)
        assert data[0]["recorded_at"].startswith("2026-06-09T08:00:00")

    def test_stale_flag(self, client):
        from datetime import datetime, timedelta, timezone
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

        fresh = _row(mac="SB:00:00:00:00:01", recorded_at=fresh_ts,
                     humidity_pct=65.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        stale = _row(mac="SB:00:00:00:00:02", recorded_at=stale_ts,
                     humidity_pct=70.0, lux=None, moisture_pct=None, conductivity_us_cm=None)
        assert client.post("/sensors/ingest", json=[fresh, stale], headers=_headers()).status_code == 200

        resp = client.get("/sensors/meter/latest")
        data = {r["mac"]: r for r in resp.json()}
        assert data["SB:00:00:00:00:01"]["stale"] is False
        assert data["SB:00:00:00:00:02"]["stale"] is True


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
