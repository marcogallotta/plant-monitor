from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GrowingUnit(Base):
    __tablename__ = "growing_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    species: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    variety: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        UniqueConstraint("filename", name="photos_filename_uniq"),
        Index("photos_captured_at_idx", "captured_at"),
        # Unique so byte-identical re-uploads can't create a second row. NULLs
        # are distinct in Postgres, so Pi rows (which don't set a hash) never
        # collide with each other.
        Index("photos_content_hash_unique_idx", "content_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    metadata_path: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    original_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    location: Mapped[Optional["Location"]] = relationship("Location", lazy="raise", viewonly=True)
    growing_units: Mapped[list["GrowingUnit"]] = relationship(
        "GrowingUnit", secondary="photo_growing_units", lazy="raise", viewonly=True
    )
    labels: Mapped[list["Label"]] = relationship(
        "Label", secondary="photo_labels", lazy="raise", viewonly=True
    )


class PhotoGrowingUnit(Base):
    __tablename__ = "photo_growing_units"

    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), primary_key=True)
    growing_unit_id: Mapped[int] = mapped_column(Integer, ForeignKey("growing_units.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    location: Mapped[Optional["Location"]] = relationship("Location", lazy="raise", viewonly=True)
    growing_units: Mapped[list["GrowingUnit"]] = relationship(
        "GrowingUnit", secondary="event_growing_units", lazy="raise", viewonly=True
    )
    photos: Mapped[list["Photo"]] = relationship(
        "Photo", secondary="event_photos", lazy="raise", viewonly=True
    )


class EventGrowingUnit(Base):
    __tablename__ = "event_growing_units"

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id"), primary_key=True)
    growing_unit_id: Mapped[int] = mapped_column(Integer, ForeignKey("growing_units.id"), primary_key=True)


class EventPhoto(Base):
    __tablename__ = "event_photos"

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id"), primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), primary_key=True)


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PhotoLabel(Base):
    __tablename__ = "photo_labels"
    __table_args__ = (
        Index("photo_labels_label_id_idx", "label_id"),
    )

    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), primary_key=True)
    label_id: Mapped[int] = mapped_column(Integer, ForeignKey("labels.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PhotoAiSuggestion(Base):
    __tablename__ = "photo_ai_suggestions"
    __table_args__ = (
        Index("photo_ai_suggestions_photo_id_idx", "photo_id"),
        Index("photo_ai_suggestions_status_idx", "status"),
        CheckConstraint("status IN ('pending', 'accepted', 'edited', 'rejected', 'deleted')", name="photo_ai_suggestions_status_check"),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="photo_ai_suggestions_confidence_check"),
        CheckConstraint("suggested_rotation IS NULL OR suggested_rotation IN (0, 90, 180, 270)", name="photo_ai_suggestions_rotation_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    batch_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    x2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_plant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("growing_units.id"), nullable=True)
    suggested_plant_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_photo_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_rotation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suggested_labels: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_options: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    observation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    edited_plant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("growing_units.id"), nullable=True)
    edited_photo_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_labels: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PhotoNote(Base):
    __tablename__ = "photo_notes"
    __table_args__ = (
        CheckConstraint("x >= 0.0 AND x <= 1.0", name="photo_notes_x_range"),
        CheckConstraint("y >= 0.0 AND y <= 1.0", name="photo_notes_y_range"),
        CheckConstraint("x2 IS NULL OR (x2 >= 0.0 AND x2 <= 1.0)", name="photo_notes_x2_range"),
        CheckConstraint("y2 IS NULL OR (y2 >= 0.0 AND y2 <= 1.0)", name="photo_notes_y2_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), nullable=False)
    note_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    growing_unit_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("growing_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
