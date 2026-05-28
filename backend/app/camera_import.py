import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import get_db
from .models import Photo, PhotoGrowingUnit, PhotoNote

router = APIRouter(prefix="/camera-import")

PHOTOS_DIR = Path("data/photos")

_IMPORTABLE_EXTS = {".jpg", ".jpeg", ".arw", ".orf"}
_RAW_EXTS = {".arw", ".orf"}

_SCAN_PATH = Path(os.environ.get("IMPORT_SCAN_PATH", "/host-media"))
_MAX_FILES = int(os.environ.get("IMPORT_SCAN_MAX_FILES", "1000"))
_CACHE_TTL = int(os.environ.get("IMPORT_SCAN_CACHE_TTL_SECONDS", "600"))

# In-process scan cache: file_id -> entry dict; populated by /scan, consumed by /thumbs and /import
_cache: dict[str, dict] = {}
_cache_built_at: float = 0.0
_HMAC_SECRET = os.urandom(32)


# ---------------------------------------------------------------------------
# Shared photo save helper (used by /manual-photos and /camera-import/import)
# ---------------------------------------------------------------------------

def save_photo(
    db: Session,
    image_bytes: bytes,
    original_filename: Optional[str],
    original_size_bytes: Optional[int],
    captured_at: datetime,
    source: str,
    photo_type: Optional[str] = None,
    location_id: Optional[int] = None,
    growing_unit_ids: Optional[list[int]] = None,
    note_text: Optional[str] = None,
    rotation: int = 0,
) -> Photo:
    """Write image bytes to disk and create a Photo DB row. Commits the transaction."""
    stem = uuid.uuid4().hex
    filename = f"{stem}.jpg"
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    image_path = PHOTOS_DIR / filename
    tmp = image_path.with_suffix(".jpg.tmp")
    try:
        tmp.write_bytes(image_bytes)
        tmp.rename(image_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    photo = Photo(
        filename=filename,
        captured_at=captured_at,
        storage_path=str(image_path),
        metadata_path="",
        source=source,
        photo_type=photo_type,
        original_filename=original_filename,
        original_size_bytes=original_size_bytes,
        location_id=location_id,
        rotation=rotation % 360,
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
    return photo


# ---------------------------------------------------------------------------
# RAW embedded JPEG extraction
# ---------------------------------------------------------------------------

def _extract_embedded_jpeg(data: bytes) -> Optional[bytes]:
    """Return the largest complete JPEG (FF D8 FF … FF D9) found inside data, or None."""
    SOI = b"\xff\xd8\xff"
    EOI = b"\xff\xd9"
    best = b""
    pos = 0
    while True:
        start = data.find(SOI, pos)
        if start == -1:
            break
        end = data.find(EOI, start + 3)
        if end == -1:
            pos = start + 1
            continue
        end += 2  # include EOI bytes
        segment = data[start:end]
        if len(segment) > len(best):
            best = segment
        pos = start + 1
    return best if best else None


# ---------------------------------------------------------------------------
# Scan cache internals
# ---------------------------------------------------------------------------

def _make_file_id(resolved_path: Path, size: int, mtime_ns: int) -> str:
    msg = f"{resolved_path}:{size}:{mtime_ns}".encode()
    return hmac.new(_HMAC_SECRET, msg, hashlib.sha256).hexdigest()[:32]


def _is_safe(entry: Path, resolved_root: Path) -> bool:
    try:
        if entry.is_symlink():
            return False
        resolved = entry.resolve()
        return resolved.is_file() and resolved.is_relative_to(resolved_root)
    except Exception:
        return False


def lookup_cached_entry(file_id: str) -> Optional[dict]:
    """Return the cache entry for file_id after re-validating it on disk, or None."""
    entry = _cache.get(file_id)
    if entry is None:
        return None
    try:
        stat = entry["path"].stat()
        if stat.st_size != entry["size_bytes"] or stat.st_mtime_ns != entry["mtime_ns"]:
            return None
        if not _is_safe(entry["path"], entry["root"]):
            return None
    except OSError:
        return None
    return entry


def _build_cache(
    scan_root: Path,
    exact_imported: set[tuple[str, int]],
    name_imported: set[str],
) -> dict:
    global _cache, _cache_built_at
    _cache = {}

    if not scan_root.exists():
        return {
            "sources": [],
            "candidates": [],
            "importable_count": 0,
            "already_imported_count": 0,
            "warnings": [f"Scan path not found: {scan_root}"],
        }

    resolved_root = scan_root.resolve()
    warnings: list[str] = []
    entries_with_stat: list[tuple[Path, os.stat_result]] = []

    for entry in scan_root.iterdir():
        if entry.suffix.lower() not in _IMPORTABLE_EXTS:
            continue
        if not _is_safe(entry, resolved_root):
            warnings.append(f"Skipped unsafe path: {entry.name}")
            continue
        try:
            stat = entry.stat()
        except OSError:
            warnings.append(f"Skipped unreadable file: {entry.name}")
            continue
        entries_with_stat.append((entry, stat))

    # Sort (mtime asc, name asc) then reverse → (mtime desc, name desc) = newest first
    entries_with_stat.sort(key=lambda x: (x[1].st_mtime_ns, x[0].name))
    entries_with_stat.reverse()

    candidates: list[dict] = []
    already_imported_count = 0
    limit_hit = False

    for entry, stat in entries_with_stat:
        if len(candidates) >= _MAX_FILES:
            limit_hit = True
            break

        size = stat.st_size
        mtime_ns = stat.st_mtime_ns
        mtime_ms = mtime_ns // 1_000_000
        ext = entry.suffix.lower()
        file_id = _make_file_id(entry.resolve(), size, mtime_ns)

        already_imported = (
            (entry.name, size) in exact_imported
            or entry.name in name_imported
        )
        if already_imported:
            already_imported_count += 1

        _cache[file_id] = {
            "path": entry.resolve(),
            "root": resolved_root,
            "filename": entry.name,
            "size_bytes": size,
            "mtime_ns": mtime_ns,
            "is_raw": ext in _RAW_EXTS,
        }

        candidates.append({
            "id": file_id,
            "filename": entry.name,
            "relative_path": entry.name,
            "extension": ext,
            "size_bytes": size,
            "mtime_ms": mtime_ms,
            "captured_at": datetime.fromtimestamp(mtime_ms / 1000, tz=timezone.utc).isoformat(),
            "captured_at_source": "mtime",
            "is_raw": ext in _RAW_EXTS,
            "already_imported": already_imported,
            "thumbnail_url": f"/camera-import/thumbs/{file_id}",
        })

    if limit_hit:
        warnings.append(f"Scan limit of {_MAX_FILES} reached; some files may be omitted.")

    _cache_built_at = time.monotonic()

    importable_count = sum(1 for c in candidates if not c["already_imported"])
    return {
        "sources": [{"label": scan_root.name, "root": str(scan_root), "candidate_count": len(candidates)}],
        "candidates": candidates,
        "importable_count": importable_count,
        "already_imported_count": already_imported_count,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/scan")
def scan(
    include_imported: bool = False,
    db: Session = Depends(get_db),
):
    global _cache, _cache_built_at

    if time.monotonic() - _cache_built_at > _CACHE_TTL:
        _cache = {}

    rows = (
        db.query(Photo.original_filename, Photo.original_size_bytes)
        .filter(Photo.original_filename.isnot(None))
        .all()
    )
    exact_imported = {(name, size) for name, size in rows if size is not None}
    name_imported = {name for name, size in rows if size is None}

    result = _build_cache(_SCAN_PATH, exact_imported, name_imported)

    if not include_imported:
        result = {**result, "candidates": [c for c in result["candidates"] if not c["already_imported"]]}

    return result


@router.get("/thumbs/{file_id}")
def get_thumbnail(file_id: str):
    entry = lookup_cached_entry(file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="file not found or scan expired")

    try:
        data = entry["path"].read_bytes()
    except OSError:
        raise HTTPException(status_code=404, detail="file not found or scan expired")

    if entry["is_raw"]:
        jpeg = _extract_embedded_jpeg(data)
        if jpeg is None:
            raise HTTPException(status_code=422, detail="no embedded JPEG preview in RAW file")
        content = jpeg
    else:
        content = data

    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


class ImportRequest(BaseModel):
    file_ids: list[str]
    photo_type: Optional[str] = None
    location_id: Optional[int] = None
    growing_unit_ids: list[int] = Field(default_factory=list)
    note_text: Optional[str] = None
    rotations: dict[str, int] = Field(default_factory=dict)  # file_id -> degrees


@router.post("/import")
def import_photos(body: ImportRequest, db: Session = Depends(get_db)):
    created = []
    skipped = []
    failed = []

    for file_id in body.file_ids:
        entry = lookup_cached_entry(file_id)
        if entry is None:
            failed.append({"file_id": file_id, "reason": "not_found_or_expired"})
            continue

        try:
            raw = entry["path"].read_bytes()
        except OSError:
            failed.append({"file_id": file_id, "reason": "file_read_error"})
            continue

        if entry["is_raw"]:
            jpeg_bytes = _extract_embedded_jpeg(raw)
            if jpeg_bytes is None:
                failed.append({"file_id": file_id, "reason": "raw_preview_not_found"})
                continue
        else:
            jpeg_bytes = raw

        original_filename = entry["filename"]
        source_size = entry["size_bytes"]

        existing = (
            db.query(Photo)
            .filter(Photo.original_filename == original_filename)
            .filter(Photo.original_size_bytes == source_size)
            .first()
        )
        if existing:
            skipped.append({
                "file_id": file_id,
                "reason": "already_imported",
                "original_filename": original_filename,
            })
            continue

        captured_at = datetime.fromtimestamp(entry["mtime_ns"] / 1e9, tz=timezone.utc)

        try:
            photo = save_photo(
                db,
                jpeg_bytes,
                original_filename,
                source_size,
                captured_at,
                "sd",
                photo_type=body.photo_type,
                location_id=body.location_id,
                growing_unit_ids=body.growing_unit_ids,
                note_text=body.note_text,
                rotation=body.rotations.get(file_id, 0),
            )
            created.append({
                "file_id": file_id,
                "photo_id": photo.id,
                "filename": photo.filename,
                "original_filename": original_filename,
            })
        except Exception:
            failed.append({"file_id": file_id, "reason": "import_error"})

    return {"created": created, "skipped": skipped, "failed": failed}
