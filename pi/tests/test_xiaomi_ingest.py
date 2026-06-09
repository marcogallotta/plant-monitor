"""Unit tests for xiaomi_ingest pure-logic functions (no BLE hardware)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from unittest.mock import patch

from xiaomi_ingest import (
    _advance_state,
    _append_queue,
    _load_queue,
    _post_rows,
    _rewrite_queue,
    _since_for_mac,
    entry_datetime,
    parse_history_entry,
)


# ---------------------------------------------------------------------------
# parse_history_entry
# ---------------------------------------------------------------------------

def _make_entry(ts=1000, temp_raw=215, lux=4200, moisture=38, conductivity=142):
    data = bytearray(16)
    data[0:4] = ts.to_bytes(4, "little")
    data[4:6] = temp_raw.to_bytes(2, "little", signed=True)
    data[7:11] = lux.to_bytes(4, "little")
    data[11] = moisture
    data[12:14] = conductivity.to_bytes(2, "little")
    return bytes(data)


def test_parse_history_entry_valid():
    raw = _make_entry(ts=1000, temp_raw=215, lux=4200, moisture=38, conductivity=142)
    result = parse_history_entry(raw)
    assert result is not None
    assert result["ts"] == 1000
    assert result["temperature_c"] == pytest.approx(21.5)
    assert result["lux"] == 4200
    assert result["moisture_pct"] == 38
    assert result["conductivity_us_cm"] == 142


def test_parse_history_entry_all_ff_returns_none():
    assert parse_history_entry(b"\xff" * 16) is None


def test_parse_history_entry_ff_ts_returns_none():
    data = bytearray(16)
    data[0:4] = b"\xff\xff\xff\xff"
    assert parse_history_entry(bytes(data)) is None


def test_parse_history_entry_wrong_length_returns_none():
    assert parse_history_entry(b"\x00" * 10) is None


def test_parse_history_entry_negative_temperature():
    raw = _make_entry(ts=1000, temp_raw=-50)
    result = parse_history_entry(raw)
    assert result["temperature_c"] == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# entry_datetime
# ---------------------------------------------------------------------------

def test_entry_datetime_recent():
    wall_now = datetime(2026, 6, 9, 10, 0, 0, tzinfo=timezone.utc)
    device_now = 3600
    entry_ts = 3000
    result = entry_datetime(entry_ts, device_now, wall_now)
    assert result == wall_now - timedelta(seconds=600)


def test_entry_datetime_zero_age():
    wall_now = datetime(2026, 6, 9, 10, 0, 0, tzinfo=timezone.utc)
    result = entry_datetime(1000, 1000, wall_now)
    assert result == wall_now


# ---------------------------------------------------------------------------
# _advance_state
# ---------------------------------------------------------------------------

def test_advance_state_sets_max_per_mac():
    rows = [
        {"mac": "AA:BB", "recorded_at": "2026-06-09T08:00:00+00:00"},
        {"mac": "AA:BB", "recorded_at": "2026-06-09T09:00:00+00:00"},
        {"mac": "CC:DD", "recorded_at": "2026-06-09T07:00:00+00:00"},
    ]
    state = _advance_state({}, rows)
    assert "2026-06-09T09" in state["AA:BB"]
    assert "2026-06-09T07" in state["CC:DD"]


def test_advance_state_does_not_go_backwards():
    rows = [{"mac": "AA:BB", "recorded_at": "2026-06-09T06:00:00+00:00"}]
    existing = {"AA:BB": "2026-06-09T08:00:00+00:00"}
    state = _advance_state(existing, rows)
    assert "2026-06-09T08" in state["AA:BB"]


def test_advance_state_advances_forward():
    rows = [{"mac": "AA:BB", "recorded_at": "2026-06-09T10:00:00+00:00"}]
    existing = {"AA:BB": "2026-06-09T08:00:00+00:00"}
    state = _advance_state(existing, rows)
    assert "2026-06-09T10" in state["AA:BB"]


# ---------------------------------------------------------------------------
# _since_for_mac
# ---------------------------------------------------------------------------

def test_since_for_mac_returns_none_when_absent():
    assert _since_for_mac({}, "AA:BB") is None


def test_since_for_mac_parses_iso():
    state = {"AA:BB": "2026-06-09T08:00:00+00:00"}
    result = _since_for_mac(state, "AA:BB")
    assert result == datetime(2026, 6, 9, 8, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Queue round-trip
# ---------------------------------------------------------------------------

def test_queue_write_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.QUEUE_FILE", tmp_path / "queue.jsonl")
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)

    rows = [
        {"mac": "AA:BB", "recorded_at": "2026-06-09T08:00:00+00:00", "moisture_pct": 38},
        {"mac": "AA:BB", "recorded_at": "2026-06-09T09:00:00+00:00", "moisture_pct": 40},
    ]
    _append_queue(rows)
    loaded = _load_queue()
    assert loaded == rows


def test_queue_rewrite_removes_flushed(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.QUEUE_FILE", tmp_path / "queue.jsonl")
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)

    rows = [
        {"mac": "AA:BB", "recorded_at": "2026-06-09T08:00:00+00:00"},
        {"mac": "AA:BB", "recorded_at": "2026-06-09T09:00:00+00:00"},
    ]
    _append_queue(rows)
    _rewrite_queue([rows[1]])
    loaded = _load_queue()
    assert len(loaded) == 1
    assert loaded[0]["recorded_at"] == rows[1]["recorded_at"]


def test_rewrite_empty_removes_file(tmp_path, monkeypatch):
    queue_file = tmp_path / "queue.jsonl"
    monkeypatch.setattr("xiaomi_ingest.QUEUE_FILE", queue_file)
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)

    _append_queue([{"mac": "AA:BB", "recorded_at": "2026-06-09T08:00:00+00:00"}])
    assert queue_file.exists()
    _rewrite_queue([])
    assert not queue_file.exists()


# ---------------------------------------------------------------------------
# _post_rows
# ---------------------------------------------------------------------------

def _make_rows(n, mac="AA:BB", base_ts="2026-06-09T08:00:00+00:00"):
    return [{"mac": mac, "recorded_at": base_ts, "moisture_pct": i} for i in range(n)]


def test_post_rows_all_ok_returns_posted(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    rows = _make_rows(3)
    with patch("xiaomi_ingest._post_chunk", return_value=("ok", "")):
        posted, failed, err = _post_rows("http://x", "tok", rows)
    assert posted == rows
    assert failed == []
    assert err == ""


def test_post_rows_validation_error_quarantined_not_posted(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    rows = _make_rows(3)
    with patch("xiaomi_ingest._post_chunk", return_value=("validation_error", "bad")):
        posted, failed, err = _post_rows("http://x", "tok", rows)
    assert posted == []
    assert failed == []
    bad_file = tmp_path / "bad.jsonl"
    assert bad_file.exists()
    assert len(bad_file.read_text().splitlines()) == 3


def test_post_rows_transient_failure_returns_remaining(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    # Three chunks: ok, retry, (never attempted). failed must include chunk 1 + chunk 2.
    rows = _make_rows(3)
    responses = [("ok", ""), ("retry", "timeout")]
    call_count = 0

    def fake_post_chunk(url, token, chunk):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return r

    monkeypatch.setattr("xiaomi_ingest.CHUNK_SIZE", 1)
    with patch("xiaomi_ingest._post_chunk", side_effect=fake_post_chunk):
        posted, failed, err = _post_rows("http://x", "tok", rows)
    assert posted == [rows[0]]
    assert failed == [rows[1], rows[2]]
    assert err == "timeout"
    assert call_count == 2  # chunk 2 never attempted


def test_post_rows_mixed_ok_validation_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    rows = _make_rows(3)
    responses = [("ok", ""), ("validation_error", "bad"), ("ok", "")]
    call_count = 0

    def fake_post_chunk(url, token, chunk):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return r

    monkeypatch.setattr("xiaomi_ingest.CHUNK_SIZE", 1)
    with patch("xiaomi_ingest._post_chunk", side_effect=fake_post_chunk):
        posted, failed, err = _post_rows("http://x", "tok", rows)
    assert posted == [rows[0], rows[2]]
    assert failed == []
    bad_file = tmp_path / "bad.jsonl"
    assert bad_file.exists()
    assert len(bad_file.read_text().splitlines()) == 1


def test_load_queue_quarantines_bad_json(tmp_path, monkeypatch):
    queue_file = tmp_path / "queue.jsonl"
    bad_file = tmp_path / "bad.jsonl"
    monkeypatch.setattr("xiaomi_ingest.QUEUE_FILE", queue_file)
    monkeypatch.setattr("xiaomi_ingest.BAD_QUEUE_FILE", bad_file)
    monkeypatch.setattr("xiaomi_ingest.STATE_DIR", tmp_path)

    queue_file.write_text('{"mac":"AA:BB","recorded_at":"2026-06-09T08:00:00+00:00"}\nnot json\n')
    rows = _load_queue()
    assert len(rows) == 1
    assert bad_file.exists()
