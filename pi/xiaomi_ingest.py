"""Xiaomi Flower Care history ingest for the Pi Zero 2W.

Reads history entries from each configured Flower Care sensor via BLE,
posts them to the plant-monitoring backend, and queues them locally when
the backend is unreachable. Run hourly via plant-xiaomi.timer.

Required env vars (from .env):
    XIAOMI_SENSORS   JSON array of {"mac": "...", "name": "..."}
    INGEST_API_TOKEN bearer token for POST /sensors/ingest
    XIAOMI_BACKEND_URL  e.g. http://localhost:8001  (default http://localhost:8000)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from bleak import BleakClient, BleakScanner

HIST_CTRL_UUID = "00001a10-0000-1000-8000-00805f9b34fb"
HIST_DATA_UUID = "00001a11-0000-1000-8000-00805f9b34fb"
EPOCH_UUID = "00001a12-0000-1000-8000-00805f9b34fb"

MAX_HISTORY_ENTRIES = 325
CHUNK_SIZE = 200
BLE_CONNECT_TIMEOUT = 10.0
BLE_READ_TIMEOUT = 5.0
HTTP_TIMEOUT = 15.0

STATE_DIR = Path.home() / ".local" / "state" / "plant-monitoring"
STATE_FILE = STATE_DIR / "xiaomi_state.json"
QUEUE_FILE = STATE_DIR / "xiaomi_queue.jsonl"
BAD_QUEUE_FILE = STATE_DIR / "xiaomi_queue_bad.jsonl"


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-testable without BLE hardware)
# ---------------------------------------------------------------------------

def parse_history_entry(data: bytes) -> dict[str, Any] | None:
    if len(data) != 16:
        return None
    if data == b"\xff" * 16:
        return None
    ts = int.from_bytes(data[0:4], "little")
    if ts == 0xFFFFFFFF:
        return None
    return {
        "ts": ts,
        "temperature_c": int.from_bytes(data[4:6], "little", signed=True) / 10.0,
        "lux": int.from_bytes(data[7:11], "little"),
        "moisture_pct": data[11],
        "conductivity_us_cm": int.from_bytes(data[12:14], "little"),
    }


def entry_datetime(entry_ts: int, device_now: int, wall_now: datetime) -> datetime:
    age_s = device_now - entry_ts
    return wall_now - timedelta(seconds=age_s)


# ---------------------------------------------------------------------------
# State / queue helpers
# ---------------------------------------------------------------------------

def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict[str, str]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict[str, str]) -> None:
    _ensure_state_dir()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


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
        QUEUE_FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    elif QUEUE_FILE.exists():
        QUEUE_FILE.unlink()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post_chunk(url: str, token: str, rows: list[dict]) -> tuple[str, str]:
    """POST a chunk. Returns ('ok', ''), ('validation_error', body), or ('retry', body)."""
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


def _flush_queue(url: str, token: str, state: dict[str, str]) -> dict[str, str]:
    rows = _load_queue()
    if not rows:
        return state

    print(f"Flushing {len(rows)} queued rows", flush=True)
    # Track which chunks are resolved (ok or quarantined) by index so we can
    # rewrite without risk of removing the wrong duplicate dict.
    resolved: set[int] = set()
    for chunk_start in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_indices = list(range(chunk_start, chunk_start + len(chunk)))
        status, body = _post_chunk(url, token, chunk)
        if status == "ok":
            resolved.update(chunk_indices)
            state = _advance_state(state, chunk)
        elif status == "validation_error":
            print(f"Queue chunk rejected by backend (400/422) — quarantining {len(chunk)} rows",
                  file=sys.stderr, flush=True)
            _quarantine_lines([json.dumps(r) for r in chunk],
                              reason="backend validation error", response_body=body)
            resolved.update(chunk_indices)
        else:
            print(f"Queue flush failed (will retry next run): {body[:200]}", file=sys.stderr, flush=True)
            break

    remaining = [r for i, r in enumerate(rows) if i not in resolved]
    _rewrite_queue(remaining)
    _save_state(state)
    return state


def _post_rows(url: str, token: str, rows: list[dict]) -> tuple[list[dict], list[dict], str]:
    """POST rows in chunks.

    Returns (posted_rows, failed_rows, error). Validation errors are quarantined
    immediately (not returned for queuing). Only transient failures are returned.
    """
    posted: list[dict] = []
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        status, body = _post_chunk(url, token, chunk)
        if status == "ok":
            posted.extend(chunk)
            continue
        if status == "validation_error":
            print(f"Fresh rows rejected by backend (400/422) — quarantining {len(chunk)} rows",
                  file=sys.stderr, flush=True)
            _quarantine_lines([json.dumps(r) for r in chunk],
                              reason="backend validation error", response_body=body)
            continue
        # Transient failure: queue this and all remaining chunks
        failed = rows[i:]
        return posted, failed, body
    return posted, [], ""


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _advance_state(state: dict[str, str], rows: list[dict]) -> dict[str, str]:
    by_mac: dict[str, datetime] = {}
    for row in rows:
        mac = row["mac"]
        try:
            dt = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if mac not in by_mac or dt > by_mac[mac]:
            by_mac[mac] = dt
    for mac, dt in by_mac.items():
        existing = state.get(mac)
        if existing:
            try:
                ex_dt = datetime.fromisoformat(existing.replace("Z", "+00:00"))
                if dt <= ex_dt:
                    continue
            except Exception:
                pass
        state[mac] = dt.isoformat()
    return state


def _since_for_mac(state: dict[str, str], mac: str) -> datetime | None:
    ts = state.get(mac)
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# BLE read
# ---------------------------------------------------------------------------

async def _ble_read(client: BleakClient, uuid: str) -> bytes:
    return bytes(await asyncio.wait_for(client.read_gatt_char(uuid), timeout=BLE_READ_TIMEOUT))


async def _ble_write(client: BleakClient, uuid: str, data: bytes) -> None:
    await asyncio.wait_for(client.write_gatt_char(uuid, data, response=True), timeout=BLE_READ_TIMEOUT)


async def _find_device(mac: str, timeout: float = 60.0):
    found = asyncio.Event()
    target = None

    def _cb(device, _adv):
        nonlocal target
        if device.address.upper() == mac.upper():
            target = device
            found.set()

    async with BleakScanner(detection_callback=_cb):
        try:
            await asyncio.wait_for(found.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    if target is None:
        raise RuntimeError(f"Device {mac} not found after {timeout:.0f}s scan")
    return target


async def read_history_since(mac: str, since: datetime | None) -> list[dict]:
    rows: list[dict] = []
    device = await _find_device(mac)
    async with BleakClient(device, timeout=BLE_CONNECT_TIMEOUT) as client:
        wall_now = datetime.now(timezone.utc)
        raw_epoch = await _ble_read(client, EPOCH_UUID)
        device_now = int.from_bytes(raw_epoch, "little")

        await _ble_write(client, HIST_CTRL_UUID, b"\xA0\x00\x00")
        await asyncio.sleep(0.3)

        for idx in range(MAX_HISTORY_ENTRIES):
            cmd = bytes([0xA1, idx & 0xFF, (idx >> 8) & 0xFF])
            await _ble_write(client, HIST_CTRL_UUID, cmd)
            await asyncio.sleep(0.2)

            raw = await _ble_read(client, HIST_DATA_UUID)
            entry = parse_history_entry(raw)
            if entry is None:
                break

            age_s = device_now - entry["ts"]
            if age_s < 0:
                continue

            dt = entry_datetime(entry["ts"], device_now, wall_now)
            if since is not None and dt <= since:
                break

            rows.append({
                "mac": mac,
                "recorded_at": dt.isoformat(),
                "temperature_c": entry["temperature_c"],
                "lux": entry["lux"],
                "moisture_pct": entry["moisture_pct"],
                "conductivity_us_cm": entry["conductivity_us_cm"],
            })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(sensors: list[dict], url: str, token: str) -> None:
    state = _load_state()
    state = _flush_queue(url, token, state)

    all_new_rows: list[dict] = []
    for sensor in sensors:
        mac = sensor["mac"]
        name = sensor.get("name")
        since = _since_for_mac(state, mac)
        print(f"Reading {name or mac} (since {since})", flush=True)
        try:
            rows = await read_history_since(mac, since)
        except Exception as e:
            print(f"BLE read failed for {mac}: {e}", file=sys.stderr, flush=True)
            continue
        for row in rows:
            row["name"] = name
        print(f"  {len(rows)} new entries", flush=True)
        all_new_rows.extend(rows)

    if not all_new_rows:
        _save_state(state)
        return

    posted, failed, err = _post_rows(url, token, all_new_rows)
    if posted:
        state = _advance_state(state, posted)
    if failed:
        print(f"POST failed, queueing {len(failed)} rows: {err}", file=sys.stderr, flush=True)
        _append_queue(failed)

    _save_state(state)


def _load_config() -> tuple[list[dict], str, str]:
    raw = os.environ.get("XIAOMI_SENSORS", "")
    if not raw:
        sys.exit("XIAOMI_SENSORS not set")
    try:
        sensors = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"XIAOMI_SENSORS is not valid JSON: {e}")
    if not isinstance(sensors, list) or not sensors:
        sys.exit("XIAOMI_SENSORS must be a non-empty JSON array")

    token = os.environ.get("INGEST_API_TOKEN", "")
    if not token:
        sys.exit("INGEST_API_TOKEN not set")

    url = os.environ.get("XIAOMI_BACKEND_URL", "http://localhost:8000").rstrip("/")
    return sensors, url, token


if __name__ == "__main__":
    sensors, url, token = _load_config()
    asyncio.run(run(sensors, url, token))
