import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

_SENSOR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


@dataclass(frozen=True)
class SensorRegistryEntry:
    id: str
    mac: str
    name: str
    kind: str


def normalize_mac(mac: str) -> str:
    return mac.strip().upper()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "sensor"


def _load_env_list(name: str) -> list[dict]:
    raw = os.environ.get(name, "")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _entry_id(item: dict) -> str:
    raw = item.get("id") or item.get("slug") or item.get("name") or item.get("mac") or "sensor"
    sid = _slugify(str(raw))
    if not _SENSOR_ID_RE.fullmatch(sid):
        raise ValueError(f"invalid sensor id: {sid}")
    return sid


@lru_cache(maxsize=1)
def load_sensor_registry() -> tuple[SensorRegistryEntry, ...]:
    entries: list[SensorRegistryEntry] = []
    for env_name, kind in (("SWITCHBOT_SENSORS", "meter"), ("XIAOMI_SENSORS", "flower-care")):
        for item in _load_env_list(env_name):
            if not isinstance(item, dict) or not item.get("mac"):
                continue
            mac = normalize_mac(str(item["mac"]))
            name = str(item.get("name") or mac)
            entries.append(SensorRegistryEntry(id=_entry_id(item), mac=mac, name=name, kind=kind))

    ids: set[str] = set()
    macs: set[tuple[str, str]] = set()
    for entry in entries:
        if entry.id in ids:
            raise ValueError(f"duplicate sensor id: {entry.id}")
        ids.add(entry.id)
        key = (entry.kind, entry.mac)
        if key in macs:
            raise ValueError(f"duplicate sensor mac for {entry.kind}: {entry.mac}")
        macs.add(key)
    return tuple(entries)


def clear_sensor_registry_cache() -> None:
    load_sensor_registry.cache_clear()


def sensor_for_mac(mac: str, kind: str) -> SensorRegistryEntry | None:
    normalized = normalize_mac(mac)
    return next((entry for entry in load_sensor_registry() if entry.kind == kind and entry.mac == normalized), None)


def sensor_for_id(sensor_id: str) -> SensorRegistryEntry | None:
    return next((entry for entry in load_sensor_registry() if entry.id == sensor_id), None)


def display_id(mac: str, name: str | None, kind: str) -> str:
    entry = sensor_for_mac(mac, kind)
    if entry is not None:
        return entry.id
    return _slugify(name or mac)


def display_name(mac: str, name: str | None, kind: str) -> str:
    entry = sensor_for_mac(mac, kind)
    if entry is not None:
        return entry.name
    return name or mac
