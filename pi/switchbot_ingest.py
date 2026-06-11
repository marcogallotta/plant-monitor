"""SwitchBot Meter passive BLE ingest for the Pi.

Scans for SwitchBot Meter advertisements, decodes temperature and humidity
from the manufacturer data payload, and posts readings to the plant-monitoring
backend. Queues rows locally when the backend is unreachable.

Run every 15 minutes via plant-switchbot.timer.

Required env vars (from .env):
    SWITCHBOT_SENSORS   JSON array of {"mac": "...", "name": "..."}
    INGEST_API_TOKEN    bearer token for POST /sensors/ingest
    XIAOMI_BACKEND_URL  backend URL (default http://localhost:8000)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from bleak import BleakScanner

MANUFACTURER_ID = 2409
SCAN_DURATION = 15.0
CHUNK_SIZE = 200
HTTP_TIMEOUT = 15.0

STATE_DIR = Path.home() / ".local" / "state" / "plant-monitoring"
QUEUE_FILE = STATE_DIR / "switchbot_queue.jsonl"
BAD_QUEUE_FILE = STATE_DIR / "switchbot_queue_bad.jsonl"


# ---------------------------------------------------------------------------
# Advertisement parsing (mirrors esp32-home-display src/switchbot/protocol.cpp)
# ---------------------------------------------------------------------------

def decode_meter(payload: bytes) -> dict[str, Any] | None:
    """Decode a SwitchBot Meter manufacturer payload.

    Returns {"temperature_c": float, "humidity_pct": int} or None if the
    payload is too short, all-zero after the MAC prefix, or not a Meter.
    """
    if len(payload) < 12:
        return None
    # Bytes 0-5 are the MAC address; bytes 6-7 are device-type/mode flags.
    # Only check the three bytes we actually parse for the "uninitialized" guard.
    if all(b == 0 for b in payload[8:11]):
        return None
    decimal_byte = payload[8]
    integer_byte = payload[9]
    humidity_byte = payload[10]
    sign = 1 if (integer_byte & 0x80) else -1
    whole = integer_byte & 0x7F
    decimal = decimal_byte & 0x0F
    temperature_c = sign * (whole + decimal / 10.0)
    humidity_pct = humidity_byte & 0x7F
    # Both zero after the bytes-8-11 guard means an uninitialised payload slipped
    # through (e.g. byte 6 was non-zero but 8-10 are all zero).
    if temperature_c == 0.0 and humidity_pct == 0:
        return None
    return {"temperature_c": temperature_c, "humidity_pct": humidity_pct}


# ---------------------------------------------------------------------------
# Queue helpers (same pattern as xiaomi_ingest.py)
# ---------------------------------------------------------------------------

def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    rows = []
    bad = []
    for line in QUEUE_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(line)
    if bad:
        _quarantine_lines(bad, reason="local JSON parse error")
        _rewrite_queue(rows)
    return rows


def _append_queue(rows: list[dict]) -> None:
    _ensure_state_dir()
    with QUEUE_FILE.open("a") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _quarantine_lines(lines: list[str], reason: str, response_body: str = "") -> None:
    _ensure_state_dir()
    with BAD_QUEUE_FILE.open("a") as f:
        for line in lines:
            entry = {"line": line, "reason": reason}
            if response_body:
                entry["response"] = response_body[:500]
            f.write(json.dumps(entry) + "\n")


def _rewrite_queue(rows: list[dict]) -> None:
    if rows:
        _ensure_state_dir()
        QUEUE_FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    elif QUEUE_FILE.exists():
        QUEUE_FILE.unlink()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post_chunk(url: str, token: str, rows: list[dict]) -> tuple[str, str]:
    try:
        resp = httpx.post(
            f"{url}/sensors/ingest",
            json=rows,
            headers={"Authorization": f"Bearer {token}"},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        return "retry", str(e)
    if resp.status_code < 300:
        return "ok", ""
    if resp.status_code in (400, 422):
        return "validation_error", resp.text
    return "retry", resp.text


def _flush_queue(url: str, token: str) -> None:
    rows = _load_queue()
    if not rows:
        return
    print(f"Flushing {len(rows)} queued rows", flush=True)
    resolved: set[int] = set()
    for chunk_start in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_indices = list(range(chunk_start, chunk_start + len(chunk)))
        status, body = _post_chunk(url, token, chunk)
        if status == "ok":
            resolved.update(chunk_indices)
        elif status == "validation_error":
            print(f"Queue chunk rejected (400/422) — quarantining {len(chunk)} rows",
                  file=sys.stderr, flush=True)
            _quarantine_lines([json.dumps(r) for r in chunk],
                              reason="backend validation error", response_body=body)
            resolved.update(chunk_indices)
        else:
            print(f"Queue flush failed (retry next run): {body[:200]}", file=sys.stderr, flush=True)
            break
    remaining = [r for i, r in enumerate(rows) if i not in resolved]
    _rewrite_queue(remaining)


def _post_rows(url: str, token: str, rows: list[dict]) -> tuple[list[dict], list[dict], str]:
    posted: list[dict] = []
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        status, body = _post_chunk(url, token, chunk)
        if status == "ok":
            posted.extend(chunk)
            continue
        if status == "validation_error":
            print(f"Fresh rows rejected (400/422) — quarantining {len(chunk)} rows",
                  file=sys.stderr, flush=True)
            _quarantine_lines([json.dumps(r) for r in chunk],
                              reason="backend validation error", response_body=body)
            continue
        failed = rows[i:]
        return posted, failed, body
    return posted, [], ""


# ---------------------------------------------------------------------------
# BLE scan
# ---------------------------------------------------------------------------

async def scan_sensors(configured_macs: set[str]) -> dict[str, dict]:
    """Passive scan for SCAN_DURATION seconds. Returns {mac: decoded_reading}."""
    results: dict[str, dict] = {}

    def handler(device, adv):
        mac = device.address.upper()
        if mac not in configured_macs:
            return
        payload = adv.manufacturer_data.get(MANUFACTURER_ID)
        if payload is None:
            return
        reading = decode_meter(bytes(payload))
        if reading is not None:
            results[mac] = reading

    async with BleakScanner(detection_callback=handler):
        await asyncio.sleep(SCAN_DURATION)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(sensors: list[dict], url: str, token: str) -> None:
    _flush_queue(url, token)

    mac_to_name = {s["mac"].upper(): s.get("name") for s in sensors}
    configured_macs = set(mac_to_name.keys())

    print(f"Scanning {len(configured_macs)} sensors for {SCAN_DURATION:.0f}s", flush=True)
    try:
        readings = await scan_sensors(configured_macs)
    except Exception as e:
        print(f"BLE scan failed: {e}", file=sys.stderr, flush=True)
        return
    print(f"  {len(readings)} sensor(s) seen", flush=True)

    if not readings:
        return

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rows = [
        {
            "mac": mac,
            "name": mac_to_name[mac],
            "recorded_at": now.isoformat(),
            "temperature_c": r["temperature_c"],
            "humidity_pct": r["humidity_pct"],
        }
        for mac, r in readings.items()
    ]

    posted, failed, err = _post_rows(url, token, rows)
    if posted:
        print(f"  posted {len(posted)} row(s)", flush=True)
    if failed:
        print(f"POST failed, queueing {len(failed)} rows: {err}", file=sys.stderr, flush=True)
        _append_queue(failed)


def _load_config() -> tuple[list[dict], str, str]:
    raw = os.environ.get("SWITCHBOT_SENSORS", "")
    if not raw:
        sys.exit("SWITCHBOT_SENSORS not set")
    try:
        sensors = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"SWITCHBOT_SENSORS is not valid JSON: {e}")
    if not isinstance(sensors, list) or not sensors:
        sys.exit("SWITCHBOT_SENSORS must be a non-empty JSON array")
    for i, s in enumerate(sensors):
        if not isinstance(s, dict) or not s.get("mac"):
            sys.exit(f"SWITCHBOT_SENSORS[{i}] must be an object with a 'mac' field")

    token = os.environ.get("INGEST_API_TOKEN", "")
    if not token:
        sys.exit("INGEST_API_TOKEN not set")

    url = os.environ.get("XIAOMI_BACKEND_URL", "http://localhost:8000").rstrip("/")
    return sensors, url, token


if __name__ == "__main__":
    sensors, url, token = _load_config()
    asyncio.run(run(sensors, url, token))
