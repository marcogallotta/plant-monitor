from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensorReading
from .sensors import FLOWER_CARE_STALE_MINUTES, METER_STALE_MINUTES, _is_stale, _reading_out

router = APIRouter(prefix="/v2/sensors")

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
            "mac": r.mac,
            "name": r.name,
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
def flower_care_latest_v2(db: Session = Depends(get_db)):
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=FLOWER_CARE_STALE_MINUTES)
    rows = (
        db.query(SensorReading)
        .filter(SensorReading.humidity_pct.is_(None))
        .distinct(SensorReading.mac)
        .order_by(SensorReading.mac, SensorReading.recorded_at.desc())
        .all()
    )
    sensors = [_reading_out(r, stale=_is_stale(r.recorded_at, stale_cutoff)) for r in rows]
    return {
        "sensors": sensors,
        "retry_after_secs": _retry_after(FLOWER_CARE_INTERVAL_SECS, FLOWER_CARE_PIPELINE_BUFFER_SECS),
    }
