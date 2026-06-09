import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
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
        return v.astimezone(timezone.utc)


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
