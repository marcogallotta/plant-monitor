"""Unit tests for switchbot_ingest pure-logic functions (no BLE hardware)."""
import json

import pytest

from switchbot_ingest import (
    _append_queue,
    _load_queue,
    _post_rows,
    _rewrite_queue,
    decode_meter,
)


# ---------------------------------------------------------------------------
# decode_meter
# ---------------------------------------------------------------------------

def _make_payload(temp_whole=21, temp_decimal=5, positive=True, humidity=65,
                  extra_zeros=False) -> bytes:
    """Build a 12-byte SwitchBot Meter manufacturer payload."""
    data = bytearray(12)
    # bytes 0-5: MAC placeholder (non-zero so hasAnyDataAfterMac passes)
    data[0:6] = b"\xAA\xBB\xCC\xDD\xEE\xFF"
    # byte 6: status (arbitrary)
    data[6] = 0x4A
    # byte 7: arbitrary
    data[7] = 0x06
    # byte 8: temperature decimal nibble
    data[8] = temp_decimal & 0x0F
    # byte 9: integer + sign bit
    data[9] = (0x80 if positive else 0x00) | (temp_whole & 0x7F)
    # byte 10: humidity
    data[10] = humidity & 0x7F
    if extra_zeros:
        data[6:] = b"\x00" * 6
    return bytes(data)


def test_decode_meter_positive_temperature():
    payload = _make_payload(temp_whole=27, temp_decimal=2, positive=True, humidity=17)
    result = decode_meter(payload)
    assert result is not None
    assert result["temperature_c"] == pytest.approx(27.2)
    assert result["humidity_pct"] == 17


def test_decode_meter_negative_temperature():
    payload = _make_payload(temp_whole=3, temp_decimal=5, positive=False, humidity=80)
    result = decode_meter(payload)
    assert result is not None
    assert result["temperature_c"] == pytest.approx(-3.5)
    assert result["humidity_pct"] == 80


def test_decode_meter_zero_decimal():
    payload = _make_payload(temp_whole=20, temp_decimal=0, positive=True, humidity=50)
    result = decode_meter(payload)
    assert result["temperature_c"] == pytest.approx(20.0)


def test_decode_meter_too_short_returns_none():
    assert decode_meter(b"\xAA" * 11) is None


def test_decode_meter_all_zero_after_mac_returns_none():
    payload = _make_payload(extra_zeros=True)
    assert decode_meter(payload) is None


def test_decode_meter_zero_temp_and_humidity_returns_none():
    # A non-Meter SwitchBot device may have non-zero byte 6 but zero temp/humidity
    data = bytearray(12)
    data[0:6] = b"\xAA\xBB\xCC\xDD\xEE\xFF"
    data[6] = 0x7B  # non-zero — passes the all-zero check
    # bytes 8, 9, 10 are all zero -> temperature=0.0, humidity=0
    assert decode_meter(bytes(data)) is None


def test_decode_real_south_payload():
    # Payload captured from D5:3A:42:86:2C:63 during the Pi BLE scan
    payload = bytes.fromhex("d53a42862c634a06029b1100")
    result = decode_meter(payload)
    assert result is not None
    assert result["temperature_c"] == pytest.approx(27.2)
    assert result["humidity_pct"] == 17


def test_decode_real_bed_payload():
    # Payload captured from EC:2E:84:06:4E:9A
    payload = bytes.fromhex("ec2e84064e9ad4020098a200")
    result = decode_meter(payload)
    assert result is not None
    assert result["temperature_c"] == pytest.approx(24.0)
    assert result["humidity_pct"] == 34


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

BASE_ROW = {
    "mac": "D5:3A:42:86:2C:63",
    "name": "South",
    "recorded_at": "2026-06-11T10:00:00+00:00",
    "temperature_c": 27.2,
    "humidity_pct": 17,
}


def test_append_and_load_queue(tmp_path, monkeypatch):
    monkeypatch.setattr("switchbot_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("switchbot_ingest.QUEUE_FILE", tmp_path / "switchbot_queue.jsonl")

    from switchbot_ingest import _append_queue as append, _load_queue as load
    append([BASE_ROW])
    rows = load()
    assert len(rows) == 1
    assert rows[0]["mac"] == BASE_ROW["mac"]


def test_rewrite_queue_empty_deletes_file(tmp_path, monkeypatch):
    monkeypatch.setattr("switchbot_ingest.QUEUE_FILE", tmp_path / "switchbot_queue.jsonl")
    qfile = tmp_path / "switchbot_queue.jsonl"
    qfile.write_text(json.dumps(BASE_ROW) + "\n")

    from switchbot_ingest import _rewrite_queue as rewrite
    rewrite([])
    assert not qfile.exists()


def test_load_queue_bad_line_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr("switchbot_ingest.STATE_DIR", tmp_path)
    qfile = tmp_path / "switchbot_queue.jsonl"
    bad_file = tmp_path / "switchbot_queue_bad.jsonl"
    monkeypatch.setattr("switchbot_ingest.QUEUE_FILE", qfile)
    monkeypatch.setattr("switchbot_ingest.BAD_QUEUE_FILE", bad_file)

    qfile.write_text(json.dumps(BASE_ROW) + "\nnot-json\n")
    from switchbot_ingest import _load_queue as load
    rows = load()
    assert len(rows) == 1
    assert bad_file.exists()


# ---------------------------------------------------------------------------
# _post_rows
# ---------------------------------------------------------------------------

def _make_mock_post(status_code=200, text=""):
    import unittest.mock as mock

    class FakeResp:
        def __init__(self):
            self.status_code = status_code
            self.text = text

    def fake_post(url, **kwargs):
        return FakeResp()

    return mock.patch("httpx.post", side_effect=fake_post)


def test_post_rows_success():
    with _make_mock_post(200):
        posted, failed, err = _post_rows("http://localhost", "token", [BASE_ROW])
    assert len(posted) == 1
    assert failed == []
    assert err == ""


def test_post_rows_queues_on_transient_error():
    with _make_mock_post(503, "down"):
        posted, failed, err = _post_rows("http://localhost", "token", [BASE_ROW])
    assert posted == []
    assert len(failed) == 1


def test_post_rows_quarantines_validation_error(tmp_path, monkeypatch):
    monkeypatch.setattr("switchbot_ingest.STATE_DIR", tmp_path)
    monkeypatch.setattr("switchbot_ingest.BAD_QUEUE_FILE", tmp_path / "bad.jsonl")
    with _make_mock_post(422, "bad field"):
        posted, failed, err = _post_rows("http://localhost", "token", [BASE_ROW])
    assert posted == []
    assert failed == []
    assert (tmp_path / "bad.jsonl").exists()
