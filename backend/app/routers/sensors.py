import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Photo, SensorReading
from ..sensor_registry import display_id, display_name, sensor_for_id

router = APIRouter(prefix="/sensors")


class SensorReadingIn(BaseModel):
    mac: str
    name: Optional[str] = None
    recorded_at: datetime
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    lux: Optional[int] = None
    moisture_pct: Optional[int] = None
    conductivity_us_cm: Optional[int] = None

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("recorded_at must include a UTC offset")
        return v.astimezone(timezone.utc).replace(second=0, microsecond=0)


@router.post("/ingest")
def sensor_ingest(readings: list[SensorReadingIn], db: Session = Depends(get_db)):
    if not readings:
        return {"inserted": 0, "skipped": 0}

    now = datetime.now(timezone.utc)
    latest_recorded_at = max(r.recorded_at for r in readings)
    lag_secs = (now - latest_recorded_at).total_seconds()
    log.info("sensor_ingest mac=%s n=%d latest_recorded_at=%s lag_secs=%.1f",
             readings[0].mac, len(readings), latest_recorded_at.isoformat(), lag_secs)

    rows = [
        {
            "mac": r.mac,
            "name": r.name,
            "recorded_at": r.recorded_at,
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
            "lux": r.lux,
            "moisture_pct": r.moisture_pct,
            "conductivity_us_cm": r.conductivity_us_cm,
        }
        for r in readings
    ]

    stmt = (
        pg_insert(SensorReading)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["mac", "recorded_at"])
        .returning(SensorReading.id)
    )
    result = db.execute(stmt)
    db.commit()

    inserted = len(result.fetchall())
    skipped = len(rows) - inserted
    return {"inserted": inserted, "skipped": skipped}


FLOWER_CARE_STALE_MINUTES = 90
METER_STALE_MINUTES = 30

# TODO: tune these from sensor_ingest lag_secs log data once a few days have accumulated
METER_INTERVAL_SECS = 15 * 60
METER_PIPELINE_BUFFER_SECS = 90

FLOWER_CARE_INTERVAL_SECS = 60 * 60
FLOWER_CARE_PIPELINE_BUFFER_SECS = 120


def _is_stale(recorded_at: datetime, cutoff: datetime) -> bool:
    ts = recorded_at if recorded_at.tzinfo is not None else recorded_at.replace(tzinfo=timezone.utc)
    return ts < cutoff


def _reading_out(r, stale: Optional[bool] = None) -> dict:
    d = {
        "mac": r.mac,
        "name": r.name,
        "recorded_at": r.recorded_at.isoformat(),
        "temperature_c": r.temperature_c,
        "lux": r.lux,
        "moisture_pct": r.moisture_pct,
        "conductivity_us_cm": r.conductivity_us_cm,
    }
    if stale is not None:
        d["stale"] = stale
    return d


def _meter_reading_out(r) -> dict:
    return {
        "mac": r.mac,
        "name": r.name,
        "recorded_at": r.recorded_at.isoformat(),
        "temperature_c": r.temperature_c,
        "humidity_pct": r.humidity_pct,
    }


def _validate_ts_params(
    start_ts: Optional[datetime],
    end_ts: Optional[datetime],
    max_points: Optional[int],
):
    if start_ts is not None and start_ts.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_ts must include a UTC offset")
    if end_ts is not None and end_ts.tzinfo is None:
        raise HTTPException(status_code=422, detail="end_ts must include a UTC offset")
    if max_points is not None and (start_ts is None or end_ts is None):
        raise HTTPException(status_code=422, detail="max_points requires both start_ts and end_ts")
    start_utc = start_ts.astimezone(timezone.utc) if start_ts is not None else None
    end_utc = end_ts.astimezone(timezone.utc) if end_ts is not None else None
    return start_utc, end_utc


def _sensor_readings(mac: str, kind_filter, start_utc, end_utc, max_points, db: Session):
    if max_points is not None:
        total_secs = (end_utc - start_utc).total_seconds()
        bucket_width = max(1, math.ceil(total_secs / max_points))
        epoch_secs = func.extract("epoch", SensorReading.recorded_at - literal(start_utc))
        bucket_expr = func.floor(epoch_secs / bucket_width)
        rn = func.row_number().over(
            partition_by=bucket_expr,
            order_by=SensorReading.recorded_at.desc(),
        ).label("rn")
        subq = (
            db.query(SensorReading, rn)
            .filter(SensorReading.mac == mac)
            .filter(kind_filter)
            .filter(SensorReading.recorded_at >= start_utc)
            .filter(SensorReading.recorded_at <= end_utc)
            .subquery()
        )
        return (
            db.query(
                subq.c.mac,
                subq.c.name,
                subq.c.recorded_at,
                subq.c.temperature_c,
                subq.c.humidity_pct,
                subq.c.lux,
                subq.c.moisture_pct,
                subq.c.conductivity_us_cm,
            )
            .filter(subq.c.rn == 1)
            .order_by(subq.c.recorded_at)
            .all()
        )
    q = (
        db.query(SensorReading)
        .filter(SensorReading.mac == mac)
        .filter(kind_filter)
    )
    if start_utc is not None:
        q = q.filter(SensorReading.recorded_at >= start_utc)
    if end_utc is not None:
        q = q.filter(SensorReading.recorded_at <= end_utc)
    return q.order_by(SensorReading.recorded_at).all()


def _next_tick_secs(interval_secs: int) -> int:
    now_secs = datetime.now(timezone.utc).timestamp()
    secs_into_interval = now_secs % interval_secs
    return int(interval_secs - secs_into_interval)


def _retry_after(interval_secs: int, buffer_secs: int) -> int:
    return _next_tick_secs(interval_secs) + buffer_secs


@router.get("/meter/latest")
def meter_latest(db: Session = Depends(get_db)):
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
def flower_care_latest(db: Session = Depends(get_db)):
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
def sensor_readings(
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


@router.get("/photos/{photo_id}")
def sensor_photo_context(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    ts = photo.captured_at
    if ts is None:
        return {"available": True, "sensors": []}
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    window = timedelta(minutes=60)
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.humidity_pct.isnot(None))
        .filter(SensorReading.recorded_at >= ts - window)
        .filter(SensorReading.recorded_at <= ts + window)
        .order_by(SensorReading.mac, SensorReading.recorded_at)
        .all()
    )
    by_mac: dict = {}
    for r in readings:
        if r.mac not in by_mac:
            by_mac[r.mac] = {"name": r.name, "readings": []}
        by_mac[r.mac]["name"] = r.name
        by_mac[r.mac]["readings"].append({
            "timestamp": r.recorded_at.isoformat(),
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
        })
    return {"available": True, "sensors": list(by_mac.values())}
