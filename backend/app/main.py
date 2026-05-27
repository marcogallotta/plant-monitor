import io
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from .database import get_db
from .models import Event, EventGrowingUnit, EventPhoto, GrowingUnit, Location, Photo, PhotoGrowingUnit, PhotoNote

app = FastAPI()

PHOTOS_DIR = Path("data/photos")
_STATIC_DIR = Path(__file__).parent.parent / "static"

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((_STATIC_DIR / "index.html").read_text())

_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.jpg$")


class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class LocationOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrowingUnitCreate(BaseModel):
    name: str
    unit_type: Optional[str] = None
    species: Optional[str] = None
    variety: Optional[str] = None
    source: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None
    current_location_id: Optional[int] = None


class GrowingUnitUpdate(BaseModel):
    name: Optional[str] = None
    unit_type: Optional[str] = None
    species: Optional[str] = None
    variety: Optional[str] = None
    source: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None
    current_location_id: Optional[int] = None


class GrowingUnitOut(BaseModel):
    id: int
    name: str
    unit_type: Optional[str] = None
    species: Optional[str] = None
    variety: Optional[str] = None
    source: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None
    current_location_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrowingUnitBrief(BaseModel):
    id: int
    name: str
    unit_type: Optional[str] = None

    model_config = {"from_attributes": True}


class PhotoOut(BaseModel):
    id: int
    filename: str
    captured_at: datetime
    url: str
    source: Optional[str] = None
    photo_type: Optional[str] = None
    original_filename: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    growing_units: list[GrowingUnitBrief] = Field(default_factory=list)
    rotation: int = 0

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    note_text: str
    x: float
    y: float
    x2: Optional[float] = None
    y2: Optional[float] = None

    @field_validator("x", "y", "x2", "y2")
    @classmethod
    def must_be_normalized(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def x2_y2_must_be_paired(self) -> "NoteCreate":
        if (self.x2 is None) != (self.y2 is None):
            raise ValueError("x2 and y2 must both be provided or both omitted")
        return self


class NoteUpdate(BaseModel):
    note_text: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None

    @field_validator("x", "y", "x2", "y2")
    @classmethod
    def must_be_normalized(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def x2_y2_must_be_paired(self) -> "NoteUpdate":
        if (self.x2 is None) != (self.y2 is None):
            raise ValueError("x2 and y2 must both be provided or both omitted")
        return self


class NoteOut(BaseModel):
    id: int
    photo_id: int
    note_text: str
    x: float
    y: float
    x2: Optional[float] = None
    y2: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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

    return meta


def _upsert_photo_record(db: Session, stem: str, meta: dict) -> None:
    if db.query(Photo).filter_by(filename=f"{stem}.jpg").first():
        return
    captured_at = datetime.fromisoformat(meta["captured_at"].replace("Z", "+00:00"))
    db.add(Photo(
        filename=f"{stem}.jpg",
        captured_at=captured_at,
        storage_path=str(PHOTOS_DIR / f"{stem}.jpg"),
        metadata_path=str(PHOTOS_DIR / f"{stem}.json"),
        source="pi",
    ))
    db.flush()


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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(loc, field, value)
    loc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(loc)
    return loc


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
    for field, value in updates.items():
        setattr(unit, field, value)
    unit.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(unit)
    return unit


def _photo_out(p: Photo, db: Session) -> PhotoOut:
    location_name = None
    if p.location_id:
        loc = db.query(Location).filter_by(id=p.location_id).first()
        location_name = loc.name if loc else None
    units = (
        db.query(GrowingUnit)
        .join(PhotoGrowingUnit, PhotoGrowingUnit.growing_unit_id == GrowingUnit.id)
        .filter(PhotoGrowingUnit.photo_id == p.id)
        .all()
    )
    return PhotoOut(
        id=p.id,
        filename=p.filename,
        captured_at=p.captured_at,
        url=f"/photos/{p.filename}",
        source=p.source,
        photo_type=p.photo_type,
        original_filename=p.original_filename,
        location_id=p.location_id,
        location_name=location_name,
        growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in units],
        rotation=p.rotation,
    )


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


@app.get("/photos", response_model=list[PhotoOut])
def list_photos(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    photo_type: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    growing_unit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Photo).order_by(Photo.captured_at)
    if start is not None:
        q = q.filter(Photo.captured_at >= start)
    if end is not None:
        q = q.filter(Photo.captured_at <= end)
    if source is not None:
        q = q.filter(Photo.source == source)
    if photo_type is not None:
        q = q.filter(Photo.photo_type == photo_type)
    if location_id is not None:
        q = q.filter(Photo.location_id == location_id)
    if growing_unit_id is not None:
        q = q.join(PhotoGrowingUnit, PhotoGrowingUnit.photo_id == Photo.id).filter(
            PhotoGrowingUnit.growing_unit_id == growing_unit_id
        )
    return [_photo_out(p, db) for p in q.all()]


class PhotoClassify(BaseModel):
    photo_type: Optional[str] = None
    location_id: Optional[int] = None
    growing_unit_ids: Optional[list[int]] = None
    rotation: Optional[int] = None

    @field_validator("rotation")
    @classmethod
    def rotation_must_be_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in {0, 90, 180, 270}:
            raise ValueError("rotation must be 0, 90, 180, or 270")
        return v


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
        photo.rotation = body.rotation
    if body.growing_unit_ids is not None:
        for uid in body.growing_unit_ids:
            if not db.query(GrowingUnit).filter_by(id=uid).first():
                raise HTTPException(status_code=404, detail=f"growing unit {uid} not found")
        db.query(PhotoGrowingUnit).filter_by(photo_id=photo_id).delete()
        for uid in body.growing_unit_ids:
            db.add(PhotoGrowingUnit(photo_id=photo_id, growing_unit_id=uid))
    db.commit()
    db.refresh(photo)
    return _photo_out(photo, db)


@app.post("/manual-photos", response_model=PhotoOut, status_code=201)
async def upload_manual_photo(
    image: UploadFile = File(...),
    captured_at: Optional[str] = Form(None),
    photo_type: Optional[str] = Form(None),
    location_id: Optional[int] = Form(None),
    growing_unit_ids: Optional[List[int]] = Form(None),
    note_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if image.content_type not in {"image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=415, detail="manual uploads must be JPEG")

    _check_location_exists(location_id, db)
    for uid in (growing_unit_ids or []):
        if not db.query(GrowingUnit).filter_by(id=uid).first():
            raise HTTPException(status_code=404, detail=f"growing unit {uid} not found")

    if captured_at is not None:
        try:
            parsed_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid captured_at format")
    else:
        parsed_at = datetime.now(timezone.utc)

    image_bytes = await image.read()
    original_filename = image.filename

    stem = uuid.uuid4().hex
    filename = f"{stem}.jpg"

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    image_path = PHOTOS_DIR / filename
    tmp_path = image_path.with_suffix(".jpg.tmp")
    try:
        tmp_path.write_bytes(image_bytes)
        tmp_path.rename(image_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    photo = Photo(
        filename=filename,
        captured_at=parsed_at,
        storage_path=str(image_path),
        metadata_path="",
        source="manual",
        photo_type=photo_type,
        original_filename=original_filename,
        location_id=location_id,
    )
    db.add(photo)
    db.flush()

    for uid in (growing_unit_ids or []):
        db.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=uid))

    if note_text:
        db.add(PhotoNote(photo_id=photo.id, note_text=note_text, x=0.0, y=0.0))

    try:
        db.commit()
    except Exception:
        db.rollback()
        image_path.unlink(missing_ok=True)
        raise

    db.refresh(photo)
    return _photo_out(photo, db)


@app.post("/photos/{photo_id}/notes", response_model=NoteOut, status_code=201)
def create_note(photo_id: int, body: NoteCreate, db: Session = Depends(get_db)):
    if not db.query(Photo).filter_by(id=photo_id).first():
        raise HTTPException(status_code=404, detail="photo not found")
    note = PhotoNote(photo_id=photo_id, note_text=body.note_text, x=body.x, y=body.y, x2=body.x2, y2=body.y2)
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
    if body.note_text is not None:
        note.note_text = body.note_text
    if body.x is not None:
        note.x = body.x
    if body.y is not None:
        note.y = body.y
    if body.x2 is not None:
        note.x2 = body.x2
    if body.y2 is not None:
        note.y2 = body.y2
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


class PhotoBrief(BaseModel):
    id: int
    filename: str
    url: str

    model_config = {"from_attributes": True}


CARE_ACTION_TYPES = {"fed_liquid", "fed_worm_castings", "watered", "harvested", "potted_up", "other"}


class EventCreate(BaseModel):
    event_type: str
    event_at: Optional[datetime] = None
    note_text: Optional[str] = None
    location_id: Optional[int] = None
    growing_unit_ids: Optional[list[int]] = None
    photo_ids: Optional[list[int]] = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in CARE_ACTION_TYPES:
            raise ValueError(f"event_type must be one of {sorted(CARE_ACTION_TYPES)}")
        return v


class EventOut(BaseModel):
    id: int
    event_type: str
    event_at: datetime
    note_text: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    growing_units: list[GrowingUnitBrief] = Field(default_factory=list)
    photos: list[PhotoBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _event_out(ev: Event, db: Session) -> EventOut:
    location_name = None
    if ev.location_id:
        loc = db.query(Location).filter_by(id=ev.location_id).first()
        location_name = loc.name if loc else None
    units = (
        db.query(GrowingUnit)
        .join(EventGrowingUnit, EventGrowingUnit.growing_unit_id == GrowingUnit.id)
        .filter(EventGrowingUnit.event_id == ev.id)
        .all()
    )
    photos = (
        db.query(Photo)
        .join(EventPhoto, EventPhoto.photo_id == Photo.id)
        .filter(EventPhoto.event_id == ev.id)
        .all()
    )
    return EventOut(
        id=ev.id,
        event_type=ev.event_type,
        event_at=ev.event_at,
        note_text=ev.note_text,
        location_id=ev.location_id,
        location_name=location_name,
        growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in units],
        photos=[PhotoBrief(id=p.id, filename=p.filename, url=f"/photos/{p.filename}") for p in photos],
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    _check_location_exists(body.location_id, db)
    for uid in (body.growing_unit_ids or []):
        if not db.query(GrowingUnit).filter_by(id=uid).first():
            raise HTTPException(status_code=404, detail=f"growing unit {uid} not found")
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
    db.refresh(ev)
    return _event_out(ev, db)


@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.event_at.desc()).all()
    return [_event_out(ev, db) for ev in events]


# --- Assistant read-only API ---

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


_assistant = APIRouter(prefix="/assistant", dependencies=[Depends(_require_assistant_token)])

class AssistantSummary(BaseModel):
    photo_count: int
    unclassified_count: int
    growing_unit_count: int
    location_count: int
    event_count: int
    recent_photos: list[PhotoOut]


class PhotoContext(BaseModel):
    photo: PhotoOut
    notes: list[NoteOut]
    events: list[EventOut]


class GrowingUnitContext(BaseModel):
    growing_unit: GrowingUnitOut
    photos: list[PhotoOut]
    events: list[EventOut]


@_assistant.get("/summary", response_model=AssistantSummary)
def assistant_summary(db: Session = Depends(get_db)):
    photo_count = db.query(Photo).count()
    unclassified_count = db.query(Photo).filter(Photo.photo_type.is_(None)).count()
    growing_unit_count = db.query(GrowingUnit).count()
    location_count = db.query(Location).count()
    event_count = db.query(Event).count()
    recent = db.query(Photo).order_by(Photo.captured_at.desc()).limit(5).all()
    return AssistantSummary(
        photo_count=photo_count,
        unclassified_count=unclassified_count,
        growing_unit_count=growing_unit_count,
        location_count=location_count,
        event_count=event_count,
        recent_photos=[_photo_out(p, db) for p in recent],
    )


@_assistant.get("/photos", response_model=list[PhotoOut])
def assistant_list_photos(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    photo_type: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    growing_unit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Photo).order_by(Photo.captured_at)
    if start is not None:
        q = q.filter(Photo.captured_at >= start)
    if end is not None:
        q = q.filter(Photo.captured_at <= end)
    if source is not None:
        q = q.filter(Photo.source == source)
    if photo_type is not None:
        q = q.filter(Photo.photo_type == photo_type)
    if location_id is not None:
        q = q.filter(Photo.location_id == location_id)
    if growing_unit_id is not None:
        q = q.join(PhotoGrowingUnit, PhotoGrowingUnit.photo_id == Photo.id).filter(
            PhotoGrowingUnit.growing_unit_id == growing_unit_id
        )
    return [_photo_out(p, db) for p in q.all()]


@_assistant.get("/photos/{photo_id}/context", response_model=PhotoContext)
def assistant_photo_context(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    notes = db.query(PhotoNote).filter_by(photo_id=photo_id).all()
    events = (
        db.query(Event)
        .join(EventPhoto, EventPhoto.event_id == Event.id)
        .filter(EventPhoto.photo_id == photo_id)
        .all()
    )
    return PhotoContext(
        photo=_photo_out(photo, db),
        notes=notes,
        events=[_event_out(ev, db) for ev in events],
    )


@_assistant.get("/photos/{photo_id}/thumbnail")
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
        img = Image.open(file_path)
        img.load()
    except Exception:
        raise HTTPException(status_code=422, detail="photo file could not be decoded")
    img.thumbnail((256, 256))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@_assistant.get("/photos/{photo_id}", response_model=PhotoOut)
def assistant_get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter_by(id=photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    return _photo_out(photo, db)


@_assistant.get("/growing-units", response_model=list[GrowingUnitOut])
def assistant_list_growing_units(db: Session = Depends(get_db)):
    return db.query(GrowingUnit).order_by(GrowingUnit.name).all()


@_assistant.get("/growing-units/{unit_id}/context", response_model=GrowingUnitContext)
def assistant_growing_unit_context(unit_id: int, db: Session = Depends(get_db)):
    unit = db.query(GrowingUnit).filter_by(id=unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="growing unit not found")
    photos = (
        db.query(Photo)
        .join(PhotoGrowingUnit, PhotoGrowingUnit.photo_id == Photo.id)
        .filter(PhotoGrowingUnit.growing_unit_id == unit_id)
        .order_by(Photo.captured_at)
        .all()
    )
    events = (
        db.query(Event)
        .join(EventGrowingUnit, EventGrowingUnit.event_id == Event.id)
        .filter(EventGrowingUnit.growing_unit_id == unit_id)
        .order_by(Event.event_at.desc())
        .all()
    )
    return GrowingUnitContext(
        growing_unit=unit,
        photos=[_photo_out(p, db) for p in photos],
        events=[_event_out(ev, db) for ev in events],
    )


@_assistant.get("/locations", response_model=list[LocationOut])
def assistant_list_locations(db: Session = Depends(get_db)):
    return db.query(Location).order_by(Location.name).all()


@_assistant.get("/events", response_model=list[EventOut])
def assistant_list_events(db: Session = Depends(get_db)):
    return [_event_out(ev, db) for ev in db.query(Event).order_by(Event.event_at.desc()).all()]


@_assistant.get("/unclassified", response_model=list[PhotoOut])
def assistant_unclassified(db: Session = Depends(get_db)):
    photos = db.query(Photo).filter(Photo.photo_type.is_(None)).order_by(Photo.captured_at).all()
    return [_photo_out(p, db) for p in photos]


app.include_router(_assistant)


@app.get("/photos/{filename}")
def serve_photo(filename: str, db: Session = Depends(get_db)):
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

    return FileResponse(file_path)
