import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from .database import get_db
from .models import GrowingUnit, Location, Photo, PhotoGrowingUnit, PhotoNote

app = FastAPI()

PHOTOS_DIR = Path("data/photos")
_STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((_STATIC_DIR / "index.html").read_text())

_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")


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


@app.get("/photos/{filename}")
def serve_photo(filename: str, db: Session = Depends(get_db)):
    path = Path(filename)
    if path.suffix != ".jpg" or not _STEM_RE.match(path.stem):
        raise HTTPException(status_code=422, detail="invalid filename format")

    photo = db.query(Photo).filter_by(filename=filename).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")

    file_path = PHOTOS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="photo file not found on disk")

    return FileResponse(file_path)
