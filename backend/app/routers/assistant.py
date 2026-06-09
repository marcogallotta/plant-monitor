import base64
import io
import math
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from ..database import get_db
from ..helpers import (
    EVENT_LOAD_OPTIONS,
    PHOTO_LOAD_OPTIONS,
    ROTATION_TRANSPOSE,
    _event_out,
    _filtered_photo_query,
    _generate_thumbnail,
    _get_photo_loaded,
    _photo_out,
)
from ..models import (
    Event,
    EventGrowingUnit,
    EventPhoto,
    GrowingUnit,
    Location,
    Photo,
    PhotoGrowingUnit,
    PhotoNote,
)
from ..schemas import (
    AssistantSummary,
    EventOut,
    GrowingUnitBrief,
    GrowingUnitContext,
    GrowingUnitOut,
    LocationOut,
    NearbyPhoto,
    NoteOut,
    PhotoContext,
    PhotoOut,
    PhotoVisionContext,
)

PHOTOS_DIR = Path("data/photos")

_public_router = APIRouter(prefix="/assistant")

_bearer = HTTPBearer(auto_error=False)

_RATE_LIMIT = 60
_RATE_WINDOW = 60  # seconds
_rate_limit_store: dict[str, tuple[int, float]] = {}
_rate_limit_lock = threading.Lock()


def _check_rate_limit(token: str) -> None:
    now = time.monotonic()
    with _rate_limit_lock:
        count, window_start = _rate_limit_store.get(token, (0, now))
        if now - window_start >= _RATE_WINDOW:
            count, window_start = 0, now
        count += 1
        _rate_limit_store[token] = (count, window_start)
    if count > _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(_RATE_WINDOW)},
        )


def _require_assistant_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    token = os.environ.get("ASSISTANT_API_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="assistant API token not configured")
    if not credentials or credentials.credentials != token:
        raise HTTPException(
            status_code=401,
            detail="invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _check_rate_limit(credentials.credentials)


router = APIRouter(prefix="/assistant", dependencies=[Depends(_require_assistant_token)])


def _photo_url(filename: str) -> str:
    base = os.environ.get("PUBLIC_URL", "").rstrip("/")
    return f"{base}/assistant/photos/{filename}"


def _assistant_photo_out(p: Photo) -> PhotoOut:
    out = _photo_out(p)
    out.url = _photo_url(p.filename)
    return out


@_public_router.get("/photos/{filename}", include_in_schema=False)
def assistant_photo_file(filename: str):
    from fastapi.responses import FileResponse
    if not re.match(r'^[a-f0-9]{32}\.jpg$', filename):
        raise HTTPException(status_code=404, detail="not found")
    file_path = (PHOTOS_DIR / filename).resolve()
    try:
        file_path.relative_to(PHOTOS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(file_path, media_type="image/jpeg")


@router.get("/summary", response_model=AssistantSummary)
def assistant_summary(db: Session = Depends(get_db)):
    photo_count = db.query(Photo).count()
    unclassified_count = db.query(Photo).filter(Photo.photo_type.is_(None)).count()
    growing_unit_count = db.query(GrowingUnit).count()
    location_count = db.query(Location).count()
    event_count = db.query(Event).count()
    recent = db.query(Photo).options(*PHOTO_LOAD_OPTIONS).order_by(Photo.captured_at.desc()).limit(5).all()
    return AssistantSummary(
        photo_count=photo_count,
        unclassified_count=unclassified_count,
        growing_unit_count=growing_unit_count,
        location_count=location_count,
        event_count=event_count,
        recent_photos=[_assistant_photo_out(p) for p in recent],
    )


@router.get("/photos", response_model=list[PhotoOut])
def assistant_list_photos(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    photo_type: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    growing_unit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = _filtered_photo_query(db, start, end, source, photo_type, location_id, growing_unit_id)
    return [_assistant_photo_out(p) for p in q.all()]


@router.get("/photos/{photo_id}/context", response_model=PhotoContext)
def assistant_photo_context(photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo_loaded(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    notes = db.query(PhotoNote).filter_by(photo_id=photo_id).all()
    events = (
        db.query(Event)
        .options(*EVENT_LOAD_OPTIONS)
        .join(EventPhoto, EventPhoto.event_id == Event.id)
        .filter(EventPhoto.photo_id == photo_id)
        .all()
    )
    return PhotoContext(
        photo=_assistant_photo_out(photo),
        notes=notes,
        events=[_event_out(ev) for ev in events],
    )


@router.get("/photos/{photo_id}/thumbnail")
def assistant_photo_thumbnail(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    file_path = Path(photo.storage_path).resolve()
    try:
        file_path.relative_to(PHOTOS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="photo not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="photo file not found on disk")
    try:
        return Response(content=_generate_thumbnail(file_path, 256), media_type="image/jpeg")
    except Exception:
        raise HTTPException(status_code=422, detail="photo file could not be decoded")


@router.get("/photos/{photo_id}", response_model=PhotoOut)
def assistant_get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo_loaded(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    return _assistant_photo_out(photo)


@router.get("/photos/{photo_id}/vision-context", response_model=PhotoVisionContext)
def assistant_photo_vision_context(photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo_loaded(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    prev_photo = (
        db.query(Photo)
        .filter(Photo.captured_at < photo.captured_at)
        .order_by(Photo.captured_at.desc())
        .first()
    )
    next_photo = (
        db.query(Photo)
        .filter(Photo.captured_at > photo.captured_at)
        .order_by(Photo.captured_at.asc())
        .first()
    )
    nearby = []
    if prev_photo:
        nearby.append(NearbyPhoto(id=prev_photo.id, captured_at=prev_photo.captured_at, relation="previous"))
    if next_photo:
        nearby.append(NearbyPhoto(id=next_photo.id, captured_at=next_photo.captured_at, relation="next"))
    all_units = db.query(GrowingUnit).order_by(GrowingUnit.name).all()
    thumbnail_data_url = None
    file_path = Path(photo.storage_path).resolve()
    if file_path.exists():
        try:
            thumbnail_data_url = "data:image/jpeg;base64," + base64.b64encode(
                _generate_thumbnail(file_path, 256, quality=75)
            ).decode()
        except Exception:
            pass
    return PhotoVisionContext(
        photo_id=photo.id,
        image_url=_photo_url(photo.filename),
        thumbnail_data_url=thumbnail_data_url,
        rotation=photo.rotation,
        captured_at=photo.captured_at,
        source=photo.source,
        original_filename=photo.original_filename,
        photo_type=photo.photo_type,
        location=photo.location.name if photo.location else None,
        growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in photo.growing_units],
        labels=[l.name for l in photo.labels],
        known_growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in all_units],
        nearby_photos=nearby,
    )


@router.get("/growing-units", response_model=list[GrowingUnitOut])
def assistant_list_growing_units(db: Session = Depends(get_db)):
    return db.query(GrowingUnit).order_by(GrowingUnit.name).all()


@router.get("/growing-units/{unit_id}/context", response_model=GrowingUnitContext)
def assistant_growing_unit_context(unit_id: int, db: Session = Depends(get_db)):
    unit = db.query(GrowingUnit).filter_by(id=unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="growing unit not found")
    photos = (
        db.query(Photo)
        .options(*PHOTO_LOAD_OPTIONS)
        .join(PhotoGrowingUnit, PhotoGrowingUnit.photo_id == Photo.id)
        .filter(PhotoGrowingUnit.growing_unit_id == unit_id)
        .order_by(Photo.captured_at)
        .all()
    )
    events = (
        db.query(Event)
        .options(*EVENT_LOAD_OPTIONS)
        .join(EventGrowingUnit, EventGrowingUnit.event_id == Event.id)
        .filter(EventGrowingUnit.growing_unit_id == unit_id)
        .order_by(Event.event_at.desc())
        .all()
    )
    return GrowingUnitContext(
        growing_unit=unit,
        photos=[_assistant_photo_out(p) for p in photos],
        events=[_event_out(ev) for ev in events],
    )


@router.get("/locations", response_model=list[LocationOut])
def assistant_list_locations(db: Session = Depends(get_db)):
    return db.query(Location).order_by(Location.name).all()


@router.get("/events", response_model=list[EventOut])
def assistant_list_events(db: Session = Depends(get_db)):
    return [_event_out(ev) for ev in db.query(Event).options(*EVENT_LOAD_OPTIONS).order_by(Event.event_at.desc()).all()]


@router.get("/openapi.json", include_in_schema=False)
def assistant_openapi(request: Request):
    app = request.app
    full = get_openapi(title="Plant Monitoring Assistant API", version="1.0.0", routes=app.routes)
    assistant_paths = {k: v for k, v in full.get("paths", {}).items() if k.startswith("/assistant/")}
    assistant_paths.pop("/assistant/openapi.json", None)
    public_url = app.servers[0]["url"] if app.servers else str(request.base_url).rstrip("/")
    return JSONResponse({"openapi": full["openapi"], "info": full["info"], "servers": [{"url": public_url}], "paths": assistant_paths, "components": full.get("components", {})})


@router.get("/unclassified", response_model=list[PhotoOut])
def assistant_unclassified(db: Session = Depends(get_db)):
    photos = db.query(Photo).options(*PHOTO_LOAD_OPTIONS).filter(Photo.photo_type.is_(None)).order_by(Photo.captured_at).all()
    return [_assistant_photo_out(p) for p in photos]


_CONTACT_SHEET_MAX = 25


@router.get("/contact-sheet")
def assistant_contact_sheet(
    ids: str = Query(..., description="Comma-separated photo IDs, max 25"),
    cell_size: int = Query(default=256, ge=64, le=512),
    cols: Optional[int] = Query(default=None, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Return a labeled JPEG contact sheet for the given photo IDs.

    Response JSON: {photo_ids, cols, rows, cell_size, image_data_url}
    Cells are ordered left-to-right, top-to-bottom. Each cell is labeled with its photo ID.
    Missing or unreadable photos render as a gray placeholder.
    """
    try:
        photo_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers")
    if not photo_ids:
        raise HTTPException(status_code=422, detail="ids is required")
    if len(photo_ids) > _CONTACT_SHEET_MAX:
        raise HTTPException(status_code=422, detail=f"max {_CONTACT_SHEET_MAX} photos per contact sheet")

    photos_by_id = {
        p.id: p for p in db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
    }

    n = len(photo_ids)
    num_cols = cols if cols else max(1, math.ceil(math.sqrt(n)))
    num_rows = math.ceil(n / num_cols)

    sheet = Image.new("RGB", (num_cols * cell_size, num_rows * cell_size), color=(40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=max(12, cell_size // 16))
    except TypeError:
        font = ImageFont.load_default()

    for idx, pid in enumerate(photo_ids):
        col = idx % num_cols
        row = idx // num_cols
        ox, oy = col * cell_size, row * cell_size

        photo = photos_by_id.get(pid)
        cell_img = None
        if photo:
            file_path = Path(photo.storage_path).resolve()
            if file_path.exists():
                try:
                    with Image.open(file_path) as src:
                        src.load()
                        img = src.copy()
                    if photo.rotation and photo.rotation in ROTATION_TRANSPOSE:
                        img = img.transpose(ROTATION_TRANSPOSE[photo.rotation])
                    img.thumbnail((cell_size, cell_size))
                    cell_img = img
                except Exception:
                    pass

        if cell_img:
            # centre the thumbnail within the cell
            px = ox + (cell_size - cell_img.width) // 2
            py = oy + (cell_size - cell_img.height) // 2
            sheet.paste(cell_img, (px, py))
        else:
            draw.rectangle([ox + 4, oy + 4, ox + cell_size - 4, oy + cell_size - 4], outline=(80, 80, 80))
            draw.text((ox + cell_size // 2, oy + cell_size // 2), "missing", fill=(120, 120, 120), font=font, anchor="mm")

        # ID label — top-left corner with a dark background for readability
        label = str(pid)
        bbox = draw.textbbox((0, 0), label, font=font)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([ox, oy, ox + lw + 6, oy + lh + 4], fill=(0, 0, 0))
        draw.text((ox + 3, oy + 2), label, fill=(255, 255, 0), font=font)

    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=80)
    image_data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    return JSONResponse({
        "photo_ids": photo_ids,
        "cols": num_cols,
        "rows": num_rows,
        "cell_size": cell_size,
        "image_data_url": image_data_url,
    })
