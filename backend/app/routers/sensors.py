import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from .. import sensors as sensor_service
from ..database import get_db
from ..models import Photo

router = APIRouter(prefix="/sensors")


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
