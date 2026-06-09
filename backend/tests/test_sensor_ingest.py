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
