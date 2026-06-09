import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GrowingUnit, Label, Photo, PhotoAiSuggestion, PhotoGrowingUnit, PhotoLabel
from ..schemas import SuggestionOut

router = APIRouter(prefix="/suggestions")

VALID_STATUSES = {"pending", "accepted", "edited", "rejected", "deleted"}
VALID_ACTIONS = {"accept", "reject", "deleted"}


class SuggestionResolve(BaseModel):
    action: str
    edited_plant_name: Optional[str] = None
    edited_photo_type: Optional[str] = None
    edited_labels: Optional[list[str]] = None


class IngestResponse(BaseModel):
    inserted: int


def _suggestion_out(s: PhotoAiSuggestion, photo: Photo) -> SuggestionOut:
    return SuggestionOut(
        id=s.id,
        photo_id=s.photo_id,
        photo_url=f"/photos/{photo.filename}",
        photo_captured_at=photo.captured_at,
        photo_rotation=photo.rotation or 0,
        model=s.model,
        batch_hint=s.batch_hint,
        x=s.x,
        y=s.y,
        x2=s.x2,
        y2=s.y2,
        suggested_plant_id=s.suggested_plant_id,
        suggested_plant_name=s.suggested_plant_name,
        suggested_photo_type=s.suggested_photo_type,
        suggested_rotation=s.suggested_rotation,
        suggested_labels=s.suggested_labels,
        confidence=s.confidence,
        question=s.question,
        suggested_options=s.suggested_options,
        observation=s.observation,
        status=s.status,
        created_at=s.created_at,
    )


def _find_or_create_label(name: str, db: Session) -> Label:
    normalised = re.sub(r"\s+", "_", name.strip().lower())
    label = db.query(Label).filter_by(name=normalised).first()
    if not label:
        label = Label(name=normalised)
        db.add(label)
        db.flush()
    return label


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(
    status: str = Query(default="pending"),
    db: Session = Depends(get_db),
):
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(VALID_STATUSES)}")

    rows = (
        db.query(PhotoAiSuggestion, Photo)
        .join(Photo, Photo.id == PhotoAiSuggestion.photo_id)
        .filter(PhotoAiSuggestion.status == status)
        .order_by(PhotoAiSuggestion.created_at.asc(), PhotoAiSuggestion.id.asc())
        .all()
    )
    return [_suggestion_out(s, p) for s, p in rows]


@router.post("/ingest", response_model=IngestResponse, status_code=201)
def ingest_suggestions(
    rows: list[dict[str, Any]],
    db: Session = Depends(get_db),
):
    # reuse the script's validation + insert logic
    sys.path.insert(0, "/app")
    try:
        from scripts.ingest_suggestions import IngestError, ingest_rows
    except ImportError:
        raise HTTPException(status_code=500, detail="ingest_suggestions script not available")
    try:
        count = ingest_rows(rows, db)
    except IngestError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    return IngestResponse(inserted=count)


@router.patch("/{suggestion_id}", response_model=SuggestionOut)
def resolve_suggestion(
    suggestion_id: int,
    body: SuggestionResolve,
    db: Session = Depends(get_db),
):
    if body.action not in VALID_ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(VALID_ACTIONS)}")

    suggestion = db.query(PhotoAiSuggestion).filter_by(id=suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="suggestion not found")

    photo = db.query(Photo).filter_by(id=suggestion.photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    now = datetime.now(timezone.utc)

    if body.action == "reject":
        suggestion.status = "rejected"
        suggestion.reviewed_at = now
        db.commit()
        db.refresh(suggestion)
        return _suggestion_out(suggestion, photo)

    if body.action == "deleted":
        suggestion.status = "deleted"
        suggestion.reviewed_at = now
        db.flush()
        # delete_photo logic inline — imports kept local to avoid circular
        from ..models import EventPhoto, PhotoNote, PhotoLabel as PL, PhotoGrowingUnit as PGU
        db.query(PhotoNote).filter_by(photo_id=photo.id).delete()
        db.query(PL).filter_by(photo_id=photo.id).delete()
        db.query(PGU).filter_by(photo_id=photo.id).delete()
        db.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).delete()
        db.query(EventPhoto).filter_by(photo_id=photo.id).delete()
        db.delete(photo)
        db.commit()
        # suggestion row is gone; return a minimal shell
        from pathlib import Path
        import logging
        for p in [photo.storage_path, photo.metadata_path]:
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError as exc:
                    logging.getLogger(__name__).warning("could not delete file %s: %s", p, exc)
        return SuggestionOut(
            id=suggestion_id, photo_id=suggestion.photo_id,
            photo_url="", photo_captured_at=photo.captured_at,
            model=suggestion.model, status="deleted",
            created_at=now,
        )

    # action == "accept" (with optional inline overrides)
    plant_overridden = body.edited_plant_name is not None
    type_overridden = body.edited_photo_type is not None
    labels_overridden = body.edited_labels is not None
    has_overrides = plant_overridden or type_overridden or labels_overridden

    photo_type = body.edited_photo_type if type_overridden else suggestion.suggested_photo_type
    if photo_type:
        photo.photo_type = photo_type

    if suggestion.suggested_rotation is not None:
        photo.rotation = suggestion.suggested_rotation

    plant_name = body.edited_plant_name if plant_overridden else suggestion.suggested_plant_name
    if suggestion.suggested_plant_id and not plant_overridden:
        existing = db.query(PhotoGrowingUnit).filter_by(
            photo_id=photo.id, growing_unit_id=suggestion.suggested_plant_id
        ).first()
        if not existing:
            db.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=suggestion.suggested_plant_id))
    elif plant_name:
        normalised = plant_name.strip()
        unit = db.query(GrowingUnit).filter(GrowingUnit.name.ilike(normalised)).first()
        if not unit:
            unit = GrowingUnit(name=normalised)
            db.add(unit)
            db.flush()
        existing = db.query(PhotoGrowingUnit).filter_by(
            photo_id=photo.id, growing_unit_id=unit.id
        ).first()
        if not existing:
            db.add(PhotoGrowingUnit(photo_id=photo.id, growing_unit_id=unit.id))
        if plant_overridden:
            suggestion.edited_plant_id = unit.id

    labels = body.edited_labels if labels_overridden else (suggestion.suggested_labels or [])
    for label_name in labels:
        label = _find_or_create_label(label_name, db)
        existing = db.query(PhotoLabel).filter_by(photo_id=photo.id, label_id=label.id).first()
        if not existing:
            db.add(PhotoLabel(photo_id=photo.id, label_id=label.id))

    if type_overridden:
        suggestion.edited_photo_type = body.edited_photo_type
    if labels_overridden:
        suggestion.edited_labels = body.edited_labels

    suggestion.status = "edited" if has_overrides else "accepted"
    suggestion.reviewed_at = now
    db.commit()
    db.refresh(suggestion)
    return _suggestion_out(suggestion, photo)
