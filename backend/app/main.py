import base64
import json
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from PIL import Image, UnidentifiedImageError

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .camera_import import router as camera_import_router, save_photo, _check_growing_units_exist
from .database import get_db
from .exif import read_exif_captured_at
logger = logging.getLogger(__name__)

from .helpers import EVENT_LOAD_OPTIONS, _event_out, _filtered_photo_query, _get_event_loaded, _get_photo_loaded, _photo_out
from .models import Event, EventGrowingUnit, EventPhoto, GrowingUnit, Label, Location, Photo, PhotoAiSuggestion, PhotoGrowingUnit, PhotoLabel, PhotoNote
from .routers.assistant import router as assistant_router, _public_router as assistant_public_router
from .routers.sensors import router as sensors_router
from .routers.suggestions import router as suggestions_router
from .schemas import (
    VALID_ROTATIONS,
    EventCreate,
    EventOut,
    GrowingUnitCreate,
    GrowingUnitOut,
    GrowingUnitUpdate,
    LabelCreate,
    LabelOut,
    LocationCreate,
    LocationOut,
    LocationUpdate,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    PhotoBatchUpdate,
    PhotoClassify,
    PhotoListOut,
    PhotoOut,
)

_public_url = os.environ.get("PUBLIC_URL", "").rstrip("/")
app = FastAPI(servers=[{"url": _public_url}] if _public_url else [])
app.include_router(camera_import_router)
app.include_router(assistant_router)
app.include_router(assistant_public_router)
app.include_router(sensors_router)
app.include_router(suggestions_router)


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/assistant"):
        return await call_next(request)
    # Health check: unauthenticated so external monitors can poll it. Leaks
    # only a capture timestamp, no photo data.
    if request.url.path.startswith("/health/"):
        return await call_next(request)
    # Pi camera ingest: dedicated bearer token, scoped to photo upload only.
    ingest_token = os.environ.get("INGEST_API_TOKEN", "")
    if ingest_token and request.method == "POST" and request.url.path == "/photos":
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == ingest_token:
            return await call_next(request)
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if not password:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            _, pwd = base64.b64decode(auth[6:]).decode().split(":", 1)
            if pwd == password:
                return await call_next(request)
        except Exception:
            pass
    port = request.url.port or 80
    return Response(status_code=401, headers={"WWW-Authenticate": f'Basic realm="Plant Monitoring :{port}"'})


@app.get("/assistant-openapi.json", include_in_schema=False)
def assistant_openapi_public(request: Request):
    from fastapi.openapi.utils import get_openapi
    from fastapi.responses import JSONResponse
    full = get_openapi(title="Plant Monitoring Assistant API", version="1.0.0", routes=app.routes)
    paths = {k: v for k, v in full.get("paths", {}).items() if k.startswith("/assistant/") and k != "/assistant/openapi.json"}
    public_url = app.servers[0]["url"] if app.servers else str(request.base_url).rstrip("/")
    return JSONResponse({"openapi": full["openapi"], "info": full["info"], "servers": [{"url": public_url}], "paths": paths, "components": full.get("components", {})})

PHOTOS_DIR = Path("data/photos")
THUMBS_DIR = Path("data/thumbs")


def _invalidate_thumb_cache(filename: str) -> None:
    for p in THUMBS_DIR.rglob(f"*_{filename}"):
        p.unlink(missing_ok=True)
_STATIC_DIR = Path(__file__).parent.parent / "static"


def _parse_iso8601(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((_STATIC_DIR / "index.html").read_text())


# Dead-man's switch for the Pi capture/upload chain: a Pi photo should arrive
# every hour. If the newest source='pi' photo is older than the threshold,
# something in the chain (Pi, camera, network, upload, token) is broken.
# Returns 503 when stale so a dumb HTTP monitor can alert on status code alone.
_CAPTURE_STALE_MINUTES = int(os.environ.get("CAPTURE_STALE_MINUTES", "90"))


@app.get("/health/live")
def health_live():
    """Liveness: the app is up. Says nothing about the ingest chain."""
    return {"status": "ok"}


@app.get("/health/captures")
def health_captures(response: Response, db: Session = Depends(get_db)):
    last = db.query(func.max(Photo.captured_at)).filter(Photo.source == "pi").scalar()
    now = datetime.now(timezone.utc)
    if last is None:
        age_minutes = None
        stale = True
    else:
        # captured_at is timestamptz, so it comes back tz-aware; the guard is
        # purely defensive. Compare on raw seconds so the threshold is exact
        # (age_minutes is only rounded for display).
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_seconds = (now - last).total_seconds()
        age_minutes = round(age_seconds / 60)
        stale = age_seconds > _CAPTURE_STALE_MINUTES * 60
    if stale:
        response.status_code = 503
    return {
        "status": "stale" if stale else "ok",
        "last_capture_at": last.isoformat().replace("+00:00", "Z") if last else None,
        "age_minutes": age_minutes,
        "threshold_minutes": _CAPTURE_STALE_MINUTES,
        "now": now.isoformat().replace("+00:00", "Z"),
    }

_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.jpg$")


@app.post("/locations", response_model=LocationOut, status_code=201)
def create_location(body: LocationCreate, db: Session = Depends(get_db)):
    loc = Location(name=body.name, description=body.description)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@app.get("/locations", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db)):
    return db.query(Location).order_by(Location.name).all()


@app.get("/locations/{location_id}", response_model=LocationOut)
def get_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter_by(id=location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="location not found")
    return loc


@app.put("/locations/{location_id}", response_model=LocationOut)
def update_location(location_id: int, body: LocationUpdate, db: Session = Depends(get_db)):
    loc = db.query(Location).filter_by(id=location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="location not found")
    _apply_named_updates(loc, body.model_dump(exclude_unset=True), db)
    return loc


def _apply_named_updates(obj, updates: dict, db: Session) -> None:
    if updates.get("name") is None and "name" in updates:
        raise HTTPException(status_code=422, detail="name cannot be null")
    for field, value in updates.items():
        setattr(obj, field, value)
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)


def _check_location_exists(location_id: Optional[int], db: Session) -> None:
    if location_id is not None and not db.query(Location).filter_by(id=location_id).first():
        raise HTTPException(status_code=404, detail="location not found")


@app.post("/growing-units", response_model=GrowingUnitOut, status_code=201)
def create_growing_unit(body: GrowingUnitCreate, db: Session = Depends(get_db)):
    _check_location_exists(body.current_location_id, db)
    unit = GrowingUnit(**body.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@app.get("/growing-units", response_model=list[GrowingUnitOut])
def list_growing_units(db: Session = Depends(get_db)):
    return db.query(GrowingUnit).order_by(GrowingUnit.name).all()


@app.get("/growing-units/{unit_id}", response_model=GrowingUnitOut)
def get_growing_unit(unit_id: int, db: Session = Depends(get_db)):
    unit = db.query(GrowingUnit).filter_by(id=unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="growing unit not found")
    return unit


@app.put("/growing-units/{unit_id}", response_model=GrowingUnitOut)
def update_growing_unit(unit_id: int, body: GrowingUnitUpdate, db: Session = Depends(get_db)):
    unit = db.query(GrowingUnit).filter_by(id=unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="growing unit not found")
    updates = body.model_dump(exclude_unset=True)
    if "current_location_id" in updates:
        _check_location_exists(updates["current_location_id"], db)
    _apply_named_updates(unit, updates, db)
    return unit


def _validated_stem(image_filename: str, metadata_filename: str) -> str:
    image_path = Path(image_filename)
    meta_path = Path(metadata_filename)

    if image_path.suffix != ".jpg":
        raise HTTPException(status_code=422, detail="image filename must have .jpg extension")
    if meta_path.suffix != ".json":
        raise HTTPException(status_code=422, detail="metadata filename must have .json extension")

    image_stem = image_path.stem
    meta_stem = meta_path.stem

    if not _STEM_RE.match(image_stem):
        raise HTTPException(status_code=422, detail="image filename must match YYYY-MM-DDTHHMMSSZ.jpg")
    if not _STEM_RE.match(meta_stem):
        raise HTTPException(status_code=422, detail="metadata filename must match YYYY-MM-DDTHHMMSSZ.json")
    if image_stem != meta_stem:
        raise HTTPException(status_code=422, detail="image and metadata filenames must share the same stem")

    return image_stem


def _validated_metadata(raw: bytes, expected_image_filename: str) -> dict:
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="metadata is not valid JSON")

    if "captured_at" not in meta:
        raise HTTPException(status_code=422, detail="metadata missing 'captured_at'")
    if "filename" not in meta:
        raise HTTPException(status_code=422, detail="metadata missing 'filename'")
    if meta["filename"] != expected_image_filename:
        raise HTTPException(status_code=422, detail="metadata 'filename' does not match uploaded image filename")

    try:
        _parse_iso8601(meta["captured_at"])
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="metadata 'captured_at' is not a valid ISO 8601 timestamp")

    return meta


def _upsert_photo_record(db: Session, stem: str, meta: dict) -> None:
    if db.query(Photo).filter_by(filename=f"{stem}.jpg").first():
        return
    captured_at = _parse_iso8601(meta["captured_at"])
    db.add(Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(PHOTOS_DIR / f"{stem}.jpg"),
        metadata_path=str(PHOTOS_DIR / f"{stem}.json"),
        source="pi",
    ))
    db.flush()


@app.post("/photos")
async def upload_photo(
    image: UploadFile = File(...),
    metadata: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    stem = _validated_stem(image.filename, metadata.filename)

    image_bytes = await image.read()
    meta_bytes = await metadata.read()

    meta = _validated_metadata(meta_bytes, f"{stem}.jpg")

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    image_path = PHOTOS_DIR / f"{stem}.jpg"
    meta_path = PHOTOS_DIR / f"{stem}.json"
    image_exists = image_path.exists()
    meta_exists = meta_path.exists()

    if image_exists and meta_exists:
        _upsert_photo_record(db, stem, meta)
        db.commit()
        return {"status": "duplicate"}
    if image_exists or meta_exists:
        raise HTTPException(status_code=409, detail="partial duplicate: one of image or metadata already exists")

    image_tmp = image_path.with_suffix(".jpg.tmp")
    meta_tmp = meta_path.with_suffix(".json.tmp")
    try:
        image_tmp.write_bytes(image_bytes)
        meta_tmp.write_bytes(meta_bytes)
        image_tmp.rename(image_path)
        meta_tmp.rename(meta_path)
    except Exception:
        image_tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)
        raise

    _upsert_photo_record(db, stem, meta)
    db.commit()
    return {"status": "ok"}


@app.get("/photos", response_model=PhotoListOut)
def list_photos(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    photo_type: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    growing_unit_id: Optional[int] = Query(None),
    label_id: Optional[int] = Query(None),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = _filtered_photo_query(db, start, end, source, photo_type, location_id, growing_unit_id, label_id)
    total = q.order_by(None).count()
    photos = [_photo_out(p) for p in q.offset(offset).limit(limit).all()]
    return {"photos": photos, "total": total}


@app.put("/photos/{photo_id}", response_model=PhotoOut)
def classify_photo(photo_id: int, body: PhotoClassify, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    if "photo_type" in body.model_fields_set:
        photo.photo_type = body.photo_type
    if "location_id" in body.model_fields_set:
        _check_location_exists(body.location_id, db)
        photo.location_id = body.location_id
    if "rotation" in body.model_fields_set:
        if body.rotation is None:
            raise HTTPException(status_code=422, detail="rotation cannot be null")
        if photo.rotation != body.rotation:
            _invalidate_thumb_cache(photo.filename)
        photo.rotation = body.rotation
    if body.growing_unit_ids is not None:
        _check_growing_units_exist(body.growing_unit_ids, db)
        db.query(PhotoGrowingUnit).filter_by(photo_id=photo_id).delete()
        for uid in body.growing_unit_ids:
            db.add(PhotoGrowingUnit(photo_id=photo_id, growing_unit_id=uid))
    db.commit()
    loaded = _get_photo_loaded(db, photo_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="photo not found")
    return _photo_out(loaded)


@app.post("/photos/batch", response_model=list[PhotoOut])
def batch_update_photos(body: PhotoBatchUpdate, db: Session = Depends(get_db)):
    """Apply the same edits to many photos in one transaction.

    `photo_type` / `location_id` are set only when present in the request body
    (mirrors PUT /photos/{id}). `add_unit_ids` / `add_label_ids` are additive
    merges — they never remove existing assignments and skip duplicates.
    """
    # Dedupe up front so repeated ids don't bloat the IN(...) clauses below; the
    # query would collapse them anyway, but this keeps the payload deterministic.
    ids = list(dict.fromkeys(body.ids))
    photos = db.query(Photo).filter(Photo.id.in_(ids)).all()
    missing = sorted(set(ids) - {p.id for p in photos})
    if missing:
        raise HTTPException(status_code=404, detail=f"photo(s) not found: {missing}")

    set_type = "photo_type" in body.model_fields_set
    set_location = "location_id" in body.model_fields_set
    if set_location:
        _check_location_exists(body.location_id, db)
    if body.add_unit_ids:
        _check_growing_units_exist(body.add_unit_ids, db)
    if body.add_label_ids:
        found = {l.id for l in db.query(Label).filter(Label.id.in_(body.add_label_ids)).all()}
        missing_labels = sorted(set(body.add_label_ids) - found)
        if missing_labels:
            raise HTTPException(status_code=404, detail=f"label(s) not found: {missing_labels}")

    # Preload existing unit/label assignments for all photos in one query each,
    # so merging stays O(1) per photo rather than issuing a query per photo.
    existing_units: dict[int, set[int]] = {p.id: set() for p in photos}
    existing_labels: dict[int, set[int]] = {p.id: set() for p in photos}
    if body.add_unit_ids:
        for pid, uid in db.query(PhotoGrowingUnit.photo_id, PhotoGrowingUnit.growing_unit_id).filter(
            PhotoGrowingUnit.photo_id.in_(ids)
        ):
            existing_units[pid].add(uid)
    if body.add_label_ids:
        for pid, lid in db.query(PhotoLabel.photo_id, PhotoLabel.label_id).filter(
            PhotoLabel.photo_id.in_(ids)
        ):
            existing_labels[pid].add(lid)

    for photo in photos:
        if set_type:
            photo.photo_type = body.photo_type
        if set_location:
            photo.location_id = body.location_id
        for uid in body.add_unit_ids:
            if uid not in existing_units[photo.id]:
                db.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=uid))
                existing_units[photo.id].add(uid)  # guard against duplicate ids in the request
        for lid in body.add_label_ids:
            if lid not in existing_labels[photo.id]:
                db.add(PhotoLabel(photo_id=photo.id, label_id=lid))
                existing_labels[photo.id].add(lid)

    db.commit()
    return [_photo_out(_get_photo_loaded(db, p.id)) for p in photos]


@app.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    db.query(PhotoNote).filter_by(photo_id=photo_id).delete()
    db.query(PhotoLabel).filter_by(photo_id=photo_id).delete()
    db.query(PhotoGrowingUnit).filter_by(photo_id=photo_id).delete()
    db.query(PhotoAiSuggestion).filter_by(photo_id=photo_id).delete()
    db.query(EventPhoto).filter_by(photo_id=photo_id).delete()
    storage_path = Path(photo.storage_path) if photo.storage_path else None
    metadata_path = Path(photo.metadata_path) if photo.metadata_path else None
    filename = photo.filename
    db.delete(photo)
    db.commit()
    _invalidate_thumb_cache(filename)
    for path in filter(None, [storage_path, metadata_path]):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("could not delete file %s: %s", path, exc)

@app.post("/manual-photos", response_model=PhotoOut, status_code=201)
async def upload_manual_photo(
    image: UploadFile = File(...),
    captured_at: Optional[str] = Form(None),
    photo_type: Optional[str] = Form(None),
    location_id: Optional[int] = Form(None),
    growing_unit_ids: Optional[List[int]] = Form(None),
    note_text: Optional[str] = Form(None),
    rotation: int = Form(0),
    original_size_bytes: Optional[int] = Form(None),
    source: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if image.content_type not in {"image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=415, detail="manual uploads must be JPEG")

    _check_location_exists(location_id, db)
    _check_growing_units_exist(growing_unit_ids or [], db)

    if rotation not in VALID_ROTATIONS:
        raise HTTPException(status_code=422, detail="rotation must be 0, 90, 180, or 270")

    if captured_at is not None:
        try:
            parsed_at = _parse_iso8601(captured_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid captured_at format")
    else:
        parsed_at = datetime.now(timezone.utc)

    image_bytes = await image.read()

    # Prefer the capture instant baked into the image's EXIF over whatever the
    # client derived. The browser upload path falls back to file.lastModified
    # (the device save time, not the capture time) when its own EXIF read fails,
    # so trusting EXIF here is the authoritative fix. Only override when EXIF
    # carries a UTC offset — a bare wall-clock time is ambiguous and is left to
    # the client value rather than guessed.
    exif_at = read_exif_captured_at(image_bytes)
    if isinstance(exif_at, datetime):
        parsed_at = exif_at

    # Dedup is by content inside save_photo: a byte-identical re-upload (e.g. the
    # same phone photo shared under a different filename) returns the existing
    # row instead of creating a duplicate.
    photo, _created = save_photo(
        db,
        image_bytes,
        image.filename,
        original_size_bytes if original_size_bytes is not None else len(image_bytes),
        parsed_at,
        source or "manual",
        photo_type=photo_type,
        location_id=location_id,
        growing_unit_ids=list(growing_unit_ids) if growing_unit_ids else None,
        note_text=note_text,
        rotation=rotation,
    )
    loaded = _get_photo_loaded(db, photo.id)
    if not loaded:
        raise HTTPException(status_code=404, detail="photo not found")
    return _photo_out(loaded)


@app.post("/photos/{photo_id}/notes", response_model=NoteOut, status_code=201)
def create_note(photo_id: int, body: NoteCreate, db: Session = Depends(get_db)):
    if not db.query(Photo).filter_by(id=photo_id).first():
        raise HTTPException(status_code=404, detail="photo not found")
    if body.growing_unit_id is not None and not db.query(GrowingUnit).filter_by(id=body.growing_unit_id).first():
        raise HTTPException(status_code=404, detail="growing unit not found")
    note = PhotoNote(
        photo_id=photo_id, note_text=body.note_text, growing_unit_id=body.growing_unit_id,
        x=body.x, y=body.y, x2=body.x2, y2=body.y2,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get("/photos/{photo_id}/notes", response_model=list[NoteOut])
def list_notes(photo_id: int, db: Session = Depends(get_db)):
    if not db.query(Photo).filter_by(id=photo_id).first():
        raise HTTPException(status_code=404, detail="photo not found")
    return db.query(PhotoNote).filter_by(photo_id=photo_id).all()


@app.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteUpdate, db: Session = Depends(get_db)):
    note = db.query(PhotoNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    if "growing_unit_id" in body.model_fields_set and body.growing_unit_id is not None:
        if not db.query(GrowingUnit).filter_by(id=body.growing_unit_id).first():
            raise HTTPException(status_code=404, detail="growing unit not found")
    _note_non_nullable = {"note_text", "x", "y"}
    updates = {}
    for field in body.model_fields_set:
        value = getattr(body, field)
        if value is None and field in _note_non_nullable:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
        updates[field] = value
    proposed_x2 = updates.get("x2", note.x2)
    proposed_y2 = updates.get("y2", note.y2)
    if (proposed_x2 is None) != (proposed_y2 is None):
        raise HTTPException(status_code=422, detail="x2 and y2 must both be set or both cleared")
    proposed_text = updates.get("note_text", note.note_text)
    proposed_unit = updates.get("growing_unit_id", note.growing_unit_id)
    if proposed_text is None and proposed_unit is None:
        raise HTTPException(
            status_code=422,
            detail="a note must have note_text, a growing_unit_id, or both",
        )
    for field, value in updates.items():
        setattr(note, field, value)
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(PhotoNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    db.delete(note)
    db.commit()


@app.get("/labels", response_model=list[LabelOut])
def list_labels(db: Session = Depends(get_db)):
    usage = (
        db.query(PhotoLabel.label_id, func.count(PhotoLabel.label_id).label("cnt"))
        .group_by(PhotoLabel.label_id)
        .subquery()
    )
    return (
        db.query(Label)
        .outerjoin(usage, Label.id == usage.c.label_id)
        .order_by(func.coalesce(usage.c.cnt, 0).desc(), Label.name)
        .all()
    )


@app.post("/labels", response_model=LabelOut, status_code=201)
def create_label(body: LabelCreate, response: Response, db: Session = Depends(get_db)):
    name = re.sub(r"\s+", "_", body.name.strip().lower())
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")
    existing = db.query(Label).filter_by(name=name).first()
    if existing:
        response.status_code = 200
        return existing
    label = Label(name=name)
    db.add(label)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Label).filter_by(name=name).first()
        response.status_code = 200
        return existing
    db.refresh(label)
    return label


@app.post("/photos/{photo_id}/labels/{label_id}", response_model=PhotoOut)
def assign_label(photo_id: int, label_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    label = db.query(Label).filter_by(id=label_id).first()
    if not label:
        raise HTTPException(status_code=404, detail="label not found")
    existing = db.query(PhotoLabel).filter_by(photo_id=photo_id, label_id=label_id).first()
    if not existing:
        db.add(PhotoLabel(photo_id=photo_id, label_id=label_id))
        db.commit()
    loaded = _get_photo_loaded(db, photo_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="photo not found")
    return _photo_out(loaded)


@app.delete("/photos/{photo_id}/labels/{label_id}", status_code=204)
def remove_label(photo_id: int, label_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    row = db.query(PhotoLabel).filter_by(photo_id=photo_id, label_id=label_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="label not assigned")
    db.delete(row)
    db.commit()


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    _check_location_exists(body.location_id, db)
    _check_growing_units_exist(body.growing_unit_ids or [], db)
    for pid in (body.photo_ids or []):
        if not db.query(Photo).filter_by(id=pid).first():
            raise HTTPException(status_code=404, detail=f"photo {pid} not found")

    ev = Event(
        event_type=body.event_type,
        event_at=body.event_at or datetime.now(timezone.utc),
        note_text=body.note_text,
        location_id=body.location_id,
    )
    db.add(ev)
    db.flush()

    for uid in (body.growing_unit_ids or []):
        db.add(EventGrowingUnit(event_id=ev.id, growing_unit_id=uid))
    for pid in (body.photo_ids or []):
        db.add(EventPhoto(event_id=ev.id, photo_id=pid))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    loaded = _get_event_loaded(db, ev.id)
    if not loaded:
        raise HTTPException(status_code=404, detail="event not found")
    return _event_out(loaded)


@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).options(*EVENT_LOAD_OPTIONS).order_by(Event.event_at.desc()).all()
    return [_event_out(ev) for ev in events]


# Maps a clockwise rotation (degrees) to the PIL transpose that bakes it into the
# pixels matching the dashboard's CSS `transform: rotate(Ndeg)` (clockwise) direction.
_ROTATION_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


@app.get("/photos/export")
def export_photos(ids: str, db: Session = Depends(get_db)):
    id_list = []
    for part in ids.split(","):
        part = part.strip()
        if not part.isdigit():
            raise HTTPException(status_code=422, detail=f"invalid id: {part!r}")
        id_list.append(int(part))
    if not id_list:
        raise HTTPException(status_code=422, detail="no ids provided")

    photos = db.query(Photo).filter(Photo.id.in_(id_list)).all()
    if not photos:
        raise HTTPException(status_code=404, detail="no matching photos")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            file_path = Path(photo.storage_path).resolve()
            try:
                file_path.relative_to(PHOTOS_DIR.resolve())
            except ValueError:
                continue
            if not file_path.exists():
                continue

            transpose = _ROTATION_TRANSPOSE.get(photo.rotation)
            if transpose is not None:
                try:
                    with Image.open(file_path) as im:
                        rotated = im.transpose(transpose).convert("RGB")
                        img_buf = BytesIO()
                        rotated.save(img_buf, format="JPEG", quality=90)
                    zf.writestr(photo.filename, img_buf.getvalue())
                except (UnidentifiedImageError, OSError):
                    continue
            else:
                zf.write(file_path, photo.filename)

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=photos.zip"},
    )


@app.get("/photos/{filename}/thumbnail")
def photo_thumbnail(filename: str, size: int = Query(400, ge=1, le=1600), oriented: bool = False, db: Session = Depends(get_db)):
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=422, detail="invalid filename format")
    photo = db.query(Photo).filter_by(filename=filename).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    file_path = Path(photo.storage_path).resolve()
    try:
        file_path.relative_to(PHOTOS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="photo not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="photo file not found on disk")

    rot = photo.rotation if oriented else 0
    cache_path = THUMBS_DIR / f"{size}" / f"{rot}_{filename}"
    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})

    try:
        with Image.open(file_path) as im:
            transpose = _ROTATION_TRANSPOSE.get(photo.rotation) if oriented else None
            if transpose:
                im = im.transpose(transpose)
            im = im.convert("RGB")
            im.thumbnail((size, size))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(f".{os.getpid()}.tmp")
            im.save(tmp, format="JPEG", quality=80)
            tmp.rename(cache_path)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=422, detail="could not decode image") from exc
    return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})


@app.get("/photos/{filename}")
def serve_photo(filename: str, oriented: bool = False, db: Session = Depends(get_db)):
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=422, detail="invalid filename format")

    photo = db.query(Photo).filter_by(filename=filename).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")

    file_path = Path(photo.storage_path).resolve()
    try:
        file_path.relative_to(PHOTOS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="photo not found")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="photo file not found on disk")

    # `oriented=1` bakes the stored rotation into the returned pixels so consumers that
    # bypass the dashboard's CSS rotation (e.g. dragging a thumbnail into a browser tab)
    # see the correct orientation. The on-disk original is never modified.
    transpose = _ROTATION_TRANSPOSE.get(photo.rotation) if oriented else None
    if transpose is not None:
        try:
            with Image.open(file_path) as im:
                rotated = im.transpose(transpose).convert("RGB")
                buf = BytesIO()
                rotated.save(buf, format="JPEG", quality=90)
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=422, detail="could not decode image") from exc
        return Response(
            content=buf.getvalue(),
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=31536000"},
        )

    return FileResponse(file_path)
