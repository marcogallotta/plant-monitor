from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensorReading
from .sensors import (
    FLOWER_CARE_STALE_MINUTES,
    METER_STALE_MINUTES,
    _is_stale,
    _meter_reading_out,
    _reading_out,
    _sensor_readings,
    _validate_ts_params,
)
from ..sensor_registry import display_id, display_name, sensor_for_id

router = APIRouter(prefix="/v2/sensors")
alias_router = APIRouter(prefix="/sensors")

# TODO: tune these from sensor_ingest lag_secs log data once a few days have accumulated
METER_INTERVAL_SECS = 15 * 60
METER_PIPELINE_BUFFER_SECS = 90

FLOWER_CARE_INTERVAL_SECS = 60 * 60
FLOWER_CARE_PIPELINE_BUFFER_SECS = 120


def _next_tick_secs(interval_secs: int) -> int:
    """Seconds until the next scheduled ingest tick."""
    now_secs = datetime.now(timezone.utc).timestamp()
    secs_into_interval = now_secs % interval_secs
    return int(interval_secs - secs_into_interval)


def _retry_after(interval_secs: int, buffer_secs: int) -> int:
    return _next_tick_secs(interval_secs) + buffer_secs


@router.get("/meter/latest")
@alias_router.get("/meter/latest")
def meter_latest_v2(db: Session = Depends(get_db)):
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=METER_STALE_MINUTES)
    rows = (
        db.query(SensorReading)
        .filter(SensorReading.humidity_pct.isnot(None))
        .distinct(SensorReading.mac)
        .order_by(SensorReading.mac, SensorReading.recorded_at.desc())
        .all()
    )
    sensors = [
        {
            "id": display_id(r.mac, r.name, "meter"),
            "mac": r.mac,
            "name": display_name(r.mac, r.name, "meter"),
            "type": "meter",
            "recorded_at": r.recorded_at.isoformat(),
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
            "stale": _is_stale(r.recorded_at, stale_cutoff),
        }
        for r in rows
    ]
    return {
        "sensors": sensors,
        "retry_after_secs": _retry_after(METER_INTERVAL_SECS, METER_PIPELINE_BUFFER_SECS),
    }


@router.get("/flower-care/latest")
@alias_router.get("/flower-care/latest")
def flower_care_latest_v2(db: Session = Depends(get_db)):
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=FLOWER_CARE_STALE_MINUTES)
    rows = (
        db.query(SensorReading)
        .filter(SensorReading.humidity_pct.is_(None))
        .distinct(SensorReading.mac)
        .order_by(SensorReading.mac, SensorReading.recorded_at.desc())
        .all()
    )
    sensors = []
    for r in rows:
        row = _reading_out(r, stale=_is_stale(r.recorded_at, stale_cutoff))
        row["id"] = display_id(r.mac, r.name, "flower-care")
        row["name"] = display_name(r.mac, r.name, "flower-care")
        row["type"] = "flower-care"
        sensors.append(row)
    return {
        "sensors": sensors,
        "retry_after_secs": _retry_after(FLOWER_CARE_INTERVAL_SECS, FLOWER_CARE_PIPELINE_BUFFER_SECS),
    }


@router.get("/{sensor_id}/readings")
@alias_router.get("/{sensor_id}/readings")
def sensor_readings_v2(
    sensor_id: str,
    start_ts: datetime | None = Query(default=None),
    end_ts: datetime | None = Query(default=None),
    max_points: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    entry = sensor_for_id(sensor_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    start_utc, end_utc = _validate_ts_params(start_ts, end_ts, max_points)
    if entry.kind == "meter":
        rows = _sensor_readings(entry.mac, SensorReading.humidity_pct.isnot(None), start_utc, end_utc, max_points, db)
        return [_meter_reading_out(r) for r in rows]
    rows = _sensor_readings(entry.mac, SensorReading.humidity_pct.is_(None), start_utc, end_utc, max_points, db)
    return [_reading_out(r) for r in rows]
