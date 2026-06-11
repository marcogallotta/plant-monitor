import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from .. import sensors as sensor_service
from ..database import get_db
from ..models import Photo, SensorReading

router = APIRouter(prefix="/sensors")


class SensorReadingIn(BaseModel):
    mac: str
    name: Optional[str] = None
    recorded_at: datetime
    temperature_c: Optional[float] = None
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

    rows = [
        {
            "mac": r.mac,
            "name": r.name,
            "recorded_at": r.recorded_at,
            "temperature_c": r.temperature_c,
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


def _reading_out(r: SensorReading, stale: Optional[bool] = None) -> dict:
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


@router.get("/flower-care/latest")
def flower_care_latest(db: Session = Depends(get_db)):
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=FLOWER_CARE_STALE_MINUTES)
    rows = (
        db.query(SensorReading)
        .distinct(SensorReading.mac)
        .order_by(SensorReading.mac, SensorReading.recorded_at.desc())
        .all()
    )
    return [_reading_out(r, stale=r.recorded_at < stale_cutoff) for r in rows]


@router.get("/flower-care/{mac}/readings")
def flower_care_readings(
    mac: str,
    start_ts: Optional[datetime] = Query(default=None),
    end_ts: Optional[datetime] = Query(default=None),
    max_points: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    if start_ts is not None and start_ts.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_ts must include a UTC offset")
    if end_ts is not None and end_ts.tzinfo is None:
        raise HTTPException(status_code=422, detail="end_ts must include a UTC offset")
    if max_points is not None and (start_ts is None or end_ts is None):
        raise HTTPException(status_code=422, detail="max_points requires both start_ts and end_ts")

    start_utc = start_ts.astimezone(timezone.utc) if start_ts is not None else None
    end_utc = end_ts.astimezone(timezone.utc) if end_ts is not None else None

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
            .filter(SensorReading.recorded_at >= start_utc)
            .filter(SensorReading.recorded_at <= end_utc)
            .subquery()
        )
        rows = (
            db.query(
                subq.c.mac,
                subq.c.name,
                subq.c.recorded_at,
                subq.c.temperature_c,
                subq.c.lux,
                subq.c.moisture_pct,
                subq.c.conductivity_us_cm,
            )
            .filter(subq.c.rn == 1)
            .order_by(subq.c.recorded_at)
            .all()
        )
        return [_reading_out(r) for r in rows]

    q = db.query(SensorReading).filter(SensorReading.mac == mac)
    if start_utc is not None:
        q = q.filter(SensorReading.recorded_at >= start_utc)
    if end_utc is not None:
        q = q.filter(SensorReading.recorded_at <= end_utc)
    rows = q.order_by(SensorReading.recorded_at).all()
    return [_reading_out(r) for r in rows]


@router.get("/latest")
def sensor_latest():
    state = sensor_service.get_state()
    if state is None:
        return {"available": False, "sensors": []}
    try:
        return {"available": True, "sensors": state.latest()}
    except Exception:
        logger.warning("sensor latest() failed", exc_info=True)
        return {"available": False, "sensors": []}


@router.get("/photos/{photo_id}")
def sensor_photo_context(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    state = sensor_service.get_state()
    if state is None:
        return {"available": False, "sensors": []}
    ts = photo.captured_at
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts is None:
        return {"available": True, "sensors": []}
    try:
        id_map = state.resolve_ids()
    except Exception:
        logger.warning("sensor resolve_ids() failed", exc_info=True)
        return {"available": False, "sensors": []}
    out = []
    for sensor_cfg in state.sensors:
        mac = sensor_cfg["mac"]
        sensor_id = id_map.get(mac)
        if sensor_id is None:
            continue
        try:
            readings = state.readings_around(sensor_id, ts)
        except Exception:
            logger.warning("sensor readings_around() failed for %s", mac, exc_info=True)
            readings = []
        out.append({"name": sensor_cfg["name"], "readings": readings})
    return {"available": True, "sensors": out}
