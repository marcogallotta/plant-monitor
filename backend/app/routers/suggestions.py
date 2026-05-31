from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Photo, PhotoAiSuggestion
from ..schemas import SuggestionOut

router = APIRouter(prefix="/suggestions")

VALID_STATUSES = {"pending", "accepted", "edited", "rejected", "deleted"}


def _suggestion_out(s: PhotoAiSuggestion, photo: Photo) -> SuggestionOut:
    return SuggestionOut(
        id=s.id,
        photo_id=s.photo_id,
        photo_url=f"/photos/{photo.filename}",
        photo_captured_at=photo.captured_at,
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
        observation=s.observation,
        status=s.status,
        created_at=s.created_at,
    )


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(
    status: str = Query(default="pending"),
    db: Session = Depends(get_db),
):
    if status not in VALID_STATUSES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(VALID_STATUSES)}")

    rows = (
        db.query(PhotoAiSuggestion, Photo)
        .join(Photo, Photo.id == PhotoAiSuggestion.photo_id)
        .filter(PhotoAiSuggestion.status == status)
        .order_by(PhotoAiSuggestion.created_at.asc(), PhotoAiSuggestion.id.asc())
        .all()
    )
    return [_suggestion_out(s, p) for s, p in rows]
