"""Tests for the sensor proxy endpoints and SensorState logic."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import app.sensors as sensors_module
from app.sensors import SensorState


@pytest.fixture(autouse=True)
def reset_sensor_state():
    sensors_module.reset_state()
    yield
    sensors_module.reset_state()


SENSORS_RESPONSE = [
    {"id": "aaaa-0001", "mac": "AA:BB:CC:DD:EE:01", "name": "South", "type": "switchbot"},
    {"id": "aaaa-0002", "mac": "AA:BB:CC:DD:EE:02", "name": "South wall", "type": "switchbot"},
    {"id": "aaaa-0003", "mac": "AA:BB:CC:DD:EE:03", "name": "West", "type": "switchbot"},
    {"id": "aaaa-0004", "mac": "AA:BB:CC:DD:EE:04", "name": "Bed", "type": "switchbot"},
]

CONFIGURED_SENSORS = [
    {"mac": "AA:BB:CC:DD:EE:01", "name": "South"},
    {"mac": "AA:BB:CC:DD:EE:02", "name": "South wall"},
    {"mac": "AA:BB:CC:DD:EE:03", "name": "West"},
]

NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
FRESH_TS = (NOW - timedelta(minutes=5)).isoformat()
STALE_TS = (NOW - timedelta(minutes=60)).isoformat()

LATEST_RESPONSE = {
    "sensors": [
        {"mac": "AA:BB:CC:DD:EE:01", "sensor_id": "aaaa-0001", "latest_timestamp": FRESH_TS, "reading": {"temperature_c": 22.5, "humidity_pct": 65.0}},
        {"mac": "AA:BB:CC:DD:EE:02", "sensor_id": "aaaa-0002", "latest_timestamp": FRESH_TS, "reading": {"temperature_c": 21.0, "humidity_pct": 70.0}},
        {"mac": "AA:BB:CC:DD:EE:03", "sensor_id": "aaaa-0003", "latest_timestamp": STALE_TS, "reading": {"temperature_c": 23.0, "humidity_pct": 60.0}},
        {"mac": "AA:BB:CC:DD:EE:04", "sensor_id": "aaaa-0004", "latest_timestamp": FRESH_TS, "reading": {"temperature_c": 19.0, "humidity_pct": 50.0}},
    ]
}

READINGS_RESPONSE = [
    {"timestamp": NOW.isoformat(), "temperature_c": 22.5, "humidity_pct": 65.0},
    {"timestamp": (NOW - timedelta(minutes=30)).isoformat(), "temperature_c": 22.0, "humidity_pct": 64.0},
]


def _make_http_response(data):
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def _make_state():
    return SensorState(
        api_url="https://sensor.local:8000",
        api_key="testkey",
        sensors=CONFIGURED_SENSORS,
    )


class TestResolveIds:
    def test_matches_configured_macs(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(SENSORS_RESPONSE)
            mock_client_factory.return_value = ctx

            result = state.resolve_ids()

        assert result == {
            "AA:BB:CC:DD:EE:01": "aaaa-0001",
            "AA:BB:CC:DD:EE:02": "aaaa-0002",
            "AA:BB:CC:DD:EE:03": "aaaa-0003",
        }

    def test_excludes_unconfigured_sensors(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(SENSORS_RESPONSE)
            mock_client_factory.return_value = ctx

            result = state.resolve_ids()

        assert "AA:BB:CC:DD:EE:04" not in result  # Bed not configured

    def test_caches_result(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(SENSORS_RESPONSE)
            mock_client_factory.return_value = ctx

            state.resolve_ids()
            state.resolve_ids()

        assert mock_client_factory.call_count == 1


class TestLatest:
    def test_returns_configured_sensors_only(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(LATEST_RESPONSE)
            mock_client_factory.return_value = ctx

            with patch("app.sensors.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.fromisoformat = datetime.fromisoformat
                result = state.latest()

        names = [r["name"] for r in result]
        assert "South" in names
        assert "South wall" in names
        assert "West" in names
        assert "Bed" not in names

    def test_fresh_reading_not_stale(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(LATEST_RESPONSE)
            mock_client_factory.return_value = ctx

            with patch("app.sensors.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.fromisoformat = datetime.fromisoformat
                result = state.latest()

        south = next(r for r in result if r["name"] == "South")
        assert south["stale"] is False
        assert south["temperature_c"] == 22.5
        assert south["humidity_pct"] == 65.0

    def test_old_reading_is_stale(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(LATEST_RESPONSE)
            mock_client_factory.return_value = ctx

            with patch("app.sensors.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.fromisoformat = datetime.fromisoformat
                result = state.latest()

        west = next(r for r in result if r["name"] == "West")
        assert west["stale"] is True


class TestReadingsAround:
    def test_calls_correct_endpoint_with_time_window(self):
        state = _make_state()
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(READINGS_RESPONSE)
            mock_client_factory.return_value = ctx

            result = state.readings_around("aaaa-0001", NOW)

        ctx.get.assert_called_once()
        call_args = ctx.get.call_args
        assert "/sensors/aaaa-0001/readings" in call_args[0][0]
        params = call_args[1]["params"]
        assert "start_ts" in params
        assert "end_ts" in params
        assert result == READINGS_RESPONSE


class TestGetState:
    def test_returns_none_when_no_url(self):
        with patch.dict("os.environ", {}, clear=True):
            result = sensors_module.get_state()
        assert result is None

    def test_returns_state_when_configured(self):
        env = {
            "SENSOR_API_URL": "https://sensor.local:8000",
            "SENSOR_API_KEY": "testkey",
            "SENSOR_SENSORS": json.dumps(CONFIGURED_SENSORS),
        }
        with patch.dict("os.environ", env):
            result = sensors_module.get_state()
        assert result is not None
        assert result.api_url == "https://sensor.local:8000"
        assert len(result.sensors) == 3

    def test_returns_none_on_invalid_sensor_json(self):
        env = {
            "SENSOR_API_URL": "https://sensor.local:8000",
            "SENSOR_API_KEY": "testkey",
            "SENSOR_SENSORS": "not-valid-json",
        }
        with patch.dict("os.environ", env):
            result = sensors_module.get_state()
        assert result is None

    def test_returns_none_when_sensors_not_a_list(self):
        env = {
            "SENSOR_API_URL": "https://sensor.local:8000",
            "SENSOR_API_KEY": "testkey",
            "SENSOR_SENSORS": '{"mac": "AA:BB:CC:DD:EE:01"}',
        }
        with patch.dict("os.environ", env):
            result = sensors_module.get_state()
        assert result is None


class TestZTimestamp:
    def test_z_suffix_parsed_as_utc(self):
        state = _make_state()
        latest_with_z = {
            "sensors": [
                {"mac": "AA:BB:CC:DD:EE:01", "sensor_id": "aaaa-0001",
                 "latest_timestamp": "2026-05-28T11:55:00Z",
                 "reading": {"temperature_c": 22.5, "humidity_pct": 65.0}},
            ]
        }
        with patch.object(state, "_client") as mock_client_factory:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get.return_value = _make_http_response(latest_with_z)
            mock_client_factory.return_value = ctx

            with patch("app.sensors.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.fromisoformat = datetime.fromisoformat
                result = state.latest()

        assert len(result) == 1
        assert result[0]["stale"] is False


class TestSensorEndpoints:
    def test_latest_unavailable_when_not_configured(self, client):
        resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["sensors"] == []

    def test_latest_unavailable_on_api_error(self, client):
        import httpx as _httpx
        state = SensorState(
            api_url="https://sensor.local:8000",
            api_key="testkey",
            sensors=CONFIGURED_SENSORS,
        )
        with patch("app.sensors.get_state", return_value=state):
            with patch.object(state, "latest", side_effect=_httpx.ConnectError("down")):
                resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_latest_returns_sensor_data(self, client):
        state = _make_state()
        with patch("app.sensors.get_state", return_value=state):
            with patch("app.sensors.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.fromisoformat = datetime.fromisoformat
                with patch.object(state, "latest", return_value=[
                    {"name": "South", "temperature_c": 22.5, "humidity_pct": 65.0, "timestamp": FRESH_TS, "stale": False}
                ]):
                    resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["sensors"]) == 1
        assert data["sensors"][0]["name"] == "South"

    def test_photo_context_404_for_missing_photo(self, client):
        resp = client.get("/sensors/photos/99999")
        assert resp.status_code == 404

    def test_photo_context_unavailable_when_not_configured(self, client, db_session):
        from app.models import Photo
        photo = Photo(
            filename="2026-01-01T120000Z.jpg",
            storage_path="/tmp/x.jpg",
            metadata_path="/tmp/x.json",
            captured_at=NOW,
            source="pi",
        )
        db_session.add(photo)
        db_session.commit()

        resp = client.get(f"/sensors/photos/{photo.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    def test_photo_context_returns_readings(self, client, db_session):
        from app.models import Photo
        photo = Photo(
            filename="2026-01-01T120001Z.jpg",
            storage_path="/tmp/y.jpg",
            metadata_path="/tmp/y.json",
            captured_at=NOW,
            source="pi",
        )
        db_session.add(photo)
        db_session.commit()

        state = _make_state()
        state._id_map = {
            "AA:BB:CC:DD:EE:01": "aaaa-0001",
            "AA:BB:CC:DD:EE:02": "aaaa-0002",
            "AA:BB:CC:DD:EE:03": "aaaa-0003",
        }
        with patch("app.sensors.get_state", return_value=state):
            with patch.object(state, "readings_around", return_value=READINGS_RESPONSE):
                resp = client.get(f"/sensors/photos/{photo.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["sensors"]) == 3
        assert data["sensors"][0]["name"] == "South"
        assert data["sensors"][0]["readings"] == READINGS_RESPONSE
