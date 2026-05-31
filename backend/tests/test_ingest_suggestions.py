from datetime import datetime, timezone

import pytest

from app.models import GrowingUnit, Photo, PhotoAiSuggestion
from scripts.ingest_suggestions import IngestError, ingest_rows


def _photo(db_session):
    photo = Photo(
        filename="2026-05-26T100000Z.jpg",
        captured_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        storage_path="/tmp/a.jpg",
        metadata_path="/tmp/a.json",
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def _row(photo_id, **kwargs):
    return {"photo_id": photo_id, "model": "claude-sonnet-4-6", **kwargs}


def test_ingest_inserts_rows(db_session):
    photo = _photo(db_session)
    count = ingest_rows([_row(photo.id, suggested_plant_name="Sorrel", confidence="high")], db_session)
    db_session.commit()
    assert count == 1
    assert db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).count() == 1


def test_ingest_sets_defaults(db_session):
    photo = _photo(db_session)
    ingest_rows([_row(photo.id)], db_session)
    db_session.commit()
    row = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).first()
    assert row.status == "pending"
    assert row.model == "claude-sonnet-4-6"


def test_ingest_multiple_rows_same_photo(db_session):
    photo = _photo(db_session)
    rows = [
        _row(photo.id, x=0.0, y=0.0, x2=0.5, y2=1.0, suggested_plant_name="Sorrel"),
        _row(photo.id, x=0.5, y=0.0, x2=1.0, y2=1.0, suggested_plant_name="Dill"),
    ]
    count = ingest_rows(rows, db_session)
    db_session.commit()
    assert count == 2
    assert db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).count() == 2


def test_ingest_missing_photo_id_raises(db_session):
    with pytest.raises(IngestError, match="missing photo_id"):
        ingest_rows([{"model": "claude-sonnet-4-6"}], db_session)


def test_ingest_missing_model_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="missing model"):
        ingest_rows([{"photo_id": photo.id}], db_session)


def test_ingest_invalid_confidence_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="invalid confidence"):
        ingest_rows([_row(photo.id, confidence="very_high")], db_session)


def test_ingest_invalid_rotation_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="invalid suggested_rotation"):
        ingest_rows([_row(photo.id, suggested_rotation=45)], db_session)


def test_ingest_unknown_photo_id_raises(db_session):
    with pytest.raises(IngestError, match="photo_id.*not found"):
        ingest_rows([_row(99999)], db_session)


def test_ingest_nothing_inserted_on_validation_error(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError):
        ingest_rows([_row(photo.id, confidence="bad")], db_session)
    assert db_session.query(PhotoAiSuggestion).count() == 0


def test_ingest_not_a_list_raises(db_session):
    with pytest.raises(IngestError, match="JSON array"):
        ingest_rows({"photo_id": 1, "model": "x"}, db_session)


def test_ingest_non_object_row_raises(db_session):
    with pytest.raises(IngestError, match="row must be an object"):
        ingest_rows([123], db_session)


def test_ingest_invalid_labels_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="suggested_labels must be a list"):
        ingest_rows([_row(photo.id, suggested_labels="wilting")], db_session)


def test_ingest_coord_out_of_range_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="x must be in 0..1"):
        ingest_rows([_row(photo.id, x=1.5, y=0.0)], db_session)


def test_ingest_unpaired_coords_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="x2 and y2 must be provided together"):
        ingest_rows([_row(photo.id, x2=0.5)], db_session)


def test_ingest_unknown_suggested_plant_id_raises(db_session):
    photo = _photo(db_session)
    with pytest.raises(IngestError, match="suggested_plant_id.*not found"):
        ingest_rows([_row(photo.id, suggested_plant_id=99999)], db_session)


def test_ingest_valid_suggested_plant_id(db_session):
    photo = _photo(db_session)
    unit = GrowingUnit(name="Sorrel")
    db_session.add(unit)
    db_session.commit()
    count = ingest_rows([_row(photo.id, suggested_plant_id=unit.id)], db_session)
    db_session.commit()
    assert count == 1
    row = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).first()
    assert row.suggested_plant_id == unit.id
