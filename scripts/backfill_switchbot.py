#!/usr/bin/env python3
"""Backfill SwitchBot history from laptop.local:8000 into the plant-monitoring backend.

Reads config from ../.env (SENSOR_API_URL, SENSOR_API_KEY, XIAOMI_BACKEND_URL,
INGEST_API_TOKEN). Paginates backwards through all readings for each SwitchBot
sensor and upserts into POST /sensors/ingest (idempotent — safe to re-run).

Usage:
    python scripts/backfill_switchbot.py [--dry-run]
"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ENV = Path(__file__).parent.parent / ".env"
if _ENV.exists():
    for _line in _ENV.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

UPSTREAM_URL = os.environ.get("SENSOR_API_URL", "https://laptop.local:8000").rstrip("/")
UPSTREAM_KEY = os.environ.get("SENSOR_API_KEY", "")
BACKEND_URL = os.environ.get("XIAOMI_BACKEND_URL", "http://localhost:8001").rstrip("/")
INGEST_TOKEN = os.environ.get("INGEST_API_TOKEN", "")

PAGE_SIZE = 100
CHUNK_SIZE = 200
PAGE_DELAY = 0.5  # seconds between upstream requests


# ---------------------------------------------------------------------------
# Upstream
# ---------------------------------------------------------------------------

def _upstream(client: httpx.Client, path: str, **params) -> object:
    for attempt in range(5):
        r = client.get(f"{UPSTREAM_URL}{path}", params=params or None, timeout=30)
        if r.status_code == 429:
            wait = PAGE_DELAY * (2 ** attempt)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def get_switchbot_sensors(client: httpx.Client) -> list[dict]:
    sensors = _upstream(client, "/sensors")
    return [s for s in sensors if s["type"] == "switchbot"]


def iter_readings(client: httpx.Client, sensor_id: str, mac: str, name: str):
    """Yield all readings oldest-first by paging backwards from now."""
    before = None
    pages = 0
    while True:
        params = {"limit": PAGE_SIZE}
        if before:
            params["before"] = before
        rows = _upstream(client, f"/sensors/{sensor_id}/readings", **params)
        if not rows:
            break
        pages += 1
        for r in rows:
            yield {
                "mac": mac,
                "name": name,
                "recorded_at": r["timestamp"],
                "temperature_c": r["temperature_c"],
                "humidity_pct": r["humidity_pct"],
            }
        if len(rows) < PAGE_SIZE:
            break
        before = rows[-1]["timestamp"]
        time.sleep(PAGE_DELAY)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

def post_chunk(client: httpx.Client, rows: list[dict]) -> dict:
    r = client.post(
        f"{BACKEND_URL}/sensors/ingest",
        json=rows,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Fetch but don't post")
    args = ap.parse_args()

    upstream = httpx.Client(
        headers={"x-api-key": UPSTREAM_KEY},
        verify=False,
    )
    backend = httpx.Client(
        headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
    )

    sensors = get_switchbot_sensors(upstream)
    if not sensors:
        print("No SwitchBot sensors found on upstream.")
        sys.exit(1)
    print(f"Found {len(sensors)} SwitchBot sensor(s): {[s['name'] for s in sensors]}")

    for sensor in sensors:
        mac = sensor["mac"]
        name = sensor["name"]
        sensor_id = sensor["id"]
        print(f"\n{name} ({mac})")

        batch: list[dict] = []
        total_inserted = total_skipped = total_fetched = 0

        for row in iter_readings(upstream, sensor_id, mac, name):
            total_fetched += 1
            batch.append(row)
            if len(batch) >= CHUNK_SIZE:
                if not args.dry_run:
                    result = post_chunk(backend, batch)
                    total_inserted += result["inserted"]
                    total_skipped += result["skipped"]
                else:
                    total_inserted += len(batch)
                batch = []

        if batch:
            if not args.dry_run:
                result = post_chunk(backend, batch)
                total_inserted += result["inserted"]
                total_skipped += result["skipped"]
            else:
                total_inserted += len(batch)

        label = "would insert" if args.dry_run else "inserted"
        print(f"  fetched={total_fetched}  {label}={total_inserted}  skipped={total_skipped}")

    print("\nDone.")


if __name__ == "__main__":
    main()
