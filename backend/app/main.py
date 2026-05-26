import json
import re
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI()

PHOTOS_DIR = Path("data/photos")

_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")


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


@app.post("/photos")
async def upload_photo(
    image: UploadFile = File(...),
    metadata: UploadFile = File(...),
):
    stem = _validated_stem(image.filename, metadata.filename)

    image_bytes = await image.read()
    meta_bytes = await metadata.read()

    _validated_metadata(meta_bytes, f"{stem}.jpg")

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    image_path = PHOTOS_DIR / f"{stem}.jpg"
    meta_path = PHOTOS_DIR / f"{stem}.json"
    image_exists = image_path.exists()
    meta_exists = meta_path.exists()

    if image_exists and meta_exists:
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

    return {"status": "ok"}
