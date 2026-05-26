import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .models import Photo

app = FastAPI()

PHOTOS_DIR = Path("data/photos")

_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")


class PhotoOut(BaseModel):
    id: int
    filename: str
    captured_at: datetime
    url: str

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


@app.get("/photos", response_model=list[PhotoOut])
def list_photos(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Photo).order_by(Photo.captured_at)
    if start is not None:
        q = q.filter(Photo.captured_at >= start)
    if end is not None:
        q = q.filter(Photo.captured_at <= end)
    return [
        PhotoOut(id=p.id, filename=p.filename, captured_at=p.captured_at, url=f"/photos/{p.filename}")
        for p in q.all()
    ]


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
