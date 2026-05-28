import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_STALE_SECONDS = 30 * 60
_WINDOW_MINUTES = 60

_state: "SensorState | None" = None


class SensorState:
    def __init__(self, api_url: str, api_key: str, sensors: list[dict[str, str]]):
        self.api_url = api_url
        self.api_key = api_key
        self.sensors = sensors  # [{"mac": "...", "name": "..."}]
        self._id_map: dict[str, str] = {}  # mac -> sensor UUID str

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api_url,
            headers={"X-Api-Key": self.api_key},
            verify=False,
            timeout=5.0,
        )

    def resolve_ids(self) -> dict[str, str]:
        if self._id_map:
            return self._id_map
        with self._client() as c:
            resp = c.get("/sensors")
            resp.raise_for_status()
        macs = {s["mac"] for s in self.sensors}
        self._id_map = {
            row["mac"]: str(row["id"])
            for row in resp.json()
            if row.get("mac") in macs
        }
        return self._id_map

    def latest(self) -> list[dict[str, Any]]:
        with self._client() as c:
            resp = c.get("/sensors/latest")
            resp.raise_for_status()
        data = resp.json()
        mac_to_name = {s["mac"]: s["name"] for s in self.sensors}
        now = datetime.now(timezone.utc)
        out = []
        for entry in data["sensors"]:
            mac = entry["mac"]
            if mac not in mac_to_name:
                continue
            ts = datetime.fromisoformat(entry["latest_timestamp"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            stale = (now - ts).total_seconds() > _STALE_SECONDS
            out.append({
                "name": mac_to_name[mac],
                "timestamp": ts.isoformat(),
                "stale": stale,
                **entry["reading"],
            })
        return out

    def readings_around(self, sensor_id: str, ts: datetime, window_minutes: int = _WINDOW_MINUTES) -> list[dict[str, Any]]:
        delta = timedelta(minutes=window_minutes)
        start = (ts - delta).isoformat()
        end = (ts + delta).isoformat()
        with self._client() as c:
            resp = c.get(
                f"/sensors/{sensor_id}/readings",
                params={"start_ts": start, "end_ts": end, "max_points": 10},
            )
            resp.raise_for_status()
        return resp.json()


def get_state() -> "SensorState | None":
    global _state
    if _state is None:
        url = os.environ.get("SENSOR_API_URL", "")
        if not url:
            return None
        key = os.environ.get("SENSOR_API_KEY", "")
        try:
            raw = json.loads(os.environ.get("SENSOR_SENSORS", "[]"))
            if not isinstance(raw, list):
                raise ValueError("SENSOR_SENSORS must be a JSON array")
        except (json.JSONDecodeError, ValueError):
            return None
        _state = SensorState(api_url=url, api_key=key, sensors=raw)
    return _state


def reset_state() -> None:
    global _state
    _state = None
