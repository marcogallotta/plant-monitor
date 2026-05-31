from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_ROTATIONS = {0, 90, 180, 270}
CARE_ACTION_TYPES = {"fed_liquid", "fed_worm_castings", "watered", "harvested", "potted_up", "propagated", "other"}


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


class GrowingUnitUpdate(BaseModel):
    name: Optional[str] = None
    unit_type: Optional[str] = None
    species: Optional[str] = None
    variety: Optional[str] = None
    source: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None
    current_location_id: Optional[int] = None


class GrowingUnitCreate(GrowingUnitUpdate):
    name: str


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


class LabelOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class PhotoOut(BaseModel):
    id: int
    filename: str
    captured_at: datetime
    url: str
    source: Optional[str] = None
    photo_type: Optional[str] = None
    original_filename: Optional[str] = None
    original_size_bytes: Optional[int] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    growing_units: list[GrowingUnitBrief] = Field(default_factory=list)
    labels: list[LabelOut] = Field(default_factory=list)
    rotation: int = 0

    model_config = {"from_attributes": True}


class PhotoListOut(BaseModel):
    photos: list[PhotoOut]
    total: int


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


class PhotoClassify(BaseModel):
    photo_type: Optional[str] = None
    location_id: Optional[int] = None
    growing_unit_ids: Optional[list[int]] = None
    rotation: Optional[int] = None

    @field_validator("rotation")
    @classmethod
    def rotation_must_be_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in VALID_ROTATIONS:
            raise ValueError("rotation must be 0, 90, 180, or 270")
        return v


class LabelCreate(BaseModel):
    name: str


class PhotoBrief(BaseModel):
    id: int
    filename: str
    url: str

    model_config = {"from_attributes": True}


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


class SuggestionOut(BaseModel):
    id: int
    photo_id: int
    photo_url: str
    photo_captured_at: datetime
    model: str
    batch_hint: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    suggested_plant_id: Optional[int] = None
    suggested_plant_name: Optional[str] = None
    suggested_photo_type: Optional[str] = None
    suggested_rotation: Optional[int] = None
    suggested_labels: Optional[list] = None
    confidence: Optional[str] = None
    question: Optional[str] = None
    observation: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


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


class NearbyPhoto(BaseModel):
    id: int
    captured_at: datetime
    relation: str


class PhotoVisionContext(BaseModel):
    photo_id: int
    image_url: str
    thumbnail_data_url: Optional[str]
    rotation: int
    captured_at: datetime
    source: Optional[str]
    original_filename: Optional[str]
    photo_type: Optional[str]
    location: Optional[str]
    growing_units: list[GrowingUnitBrief]
    labels: list[str]
    known_growing_units: list[GrowingUnitBrief]
    nearby_photos: list[NearbyPhoto]
