from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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

    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), primary_key=True)
    label_id: Mapped[int] = mapped_column(Integer, ForeignKey("labels.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
