from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .models import Event, Photo, PhotoGrowingUnit, PhotoLabel
from .schemas import EventOut, GrowingUnitBrief, LabelOut, PhotoBrief, PhotoOut

PHOTO_LOAD_OPTIONS = (
    selectinload(Photo.location),
    selectinload(Photo.growing_units),
    selectinload(Photo.labels),
)

EVENT_LOAD_OPTIONS = (
    selectinload(Event.location),
    selectinload(Event.growing_units),
    selectinload(Event.photos),
)


def _filtered_photo_query(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    source: Optional[str] = None,
    photo_type: Optional[str] = None,
    location_id: Optional[int] = None,
    growing_unit_id: Optional[int] = None,
    label_id: Optional[int] = None,
):
    q = db.query(Photo).options(*PHOTO_LOAD_OPTIONS).order_by(Photo.captured_at, Photo.id)
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
    if label_id is not None:
        q = q.join(PhotoLabel, PhotoLabel.photo_id == Photo.id).filter(
            PhotoLabel.label_id == label_id
        )
    return q


def _get_photo_loaded(db: Session, photo_id: int) -> Optional[Photo]:
    return db.query(Photo).options(*PHOTO_LOAD_OPTIONS).filter_by(id=photo_id).first()


def _get_event_loaded(db: Session, event_id: int) -> Optional[Event]:
    return db.query(Event).options(*EVENT_LOAD_OPTIONS).filter_by(id=event_id).first()


def _photo_out(p: Photo) -> PhotoOut:
    return PhotoOut(
        id=p.id,
        filename=p.filename,
        captured_at=p.captured_at,
        url=f"/photos/{p.filename}",
        source=p.source,
        photo_type=p.photo_type,
        original_filename=p.original_filename,
        original_size_bytes=p.original_size_bytes,
        location_id=p.location_id,
        location_name=p.location.name if p.location else None,
        growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in p.growing_units],
        labels=[LabelOut(id=l.id, name=l.name) for l in p.labels],
        rotation=p.rotation,
    )


def _event_out(ev: Event) -> EventOut:
    return EventOut(
        id=ev.id,
        event_type=ev.event_type,
        event_at=ev.event_at,
        note_text=ev.note_text,
        location_id=ev.location_id,
        location_name=ev.location.name if ev.location else None,
        growing_units=[GrowingUnitBrief(id=u.id, name=u.name, unit_type=u.unit_type) for u in ev.growing_units],
        photos=[PhotoBrief(id=p.id, filename=p.filename, url=f"/photos/{p.filename}") for p in ev.photos],
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )
