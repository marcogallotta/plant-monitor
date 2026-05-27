import pytest
from sqlalchemy import inspect


def test_photos_table_exists(engine):
    assert inspect(engine).has_table("photos")


def test_photos_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("photos")}
    assert cols == {
        "id", "filename", "captured_at", "storage_path", "metadata_path", "created_at",
        "source", "photo_type", "original_filename", "location_id", "rotation",
    }


def test_photos_filename_unique(engine):
    uqs = inspect(engine).get_unique_constraints("photos")
    assert any(set(uq["column_names"]) == {"filename"} for uq in uqs)


def test_photos_captured_at_indexed(engine):
    idxs = inspect(engine).get_indexes("photos")
    assert any("captured_at" in idx["column_names"] for idx in idxs)


def test_photo_notes_table_exists(engine):
    assert inspect(engine).has_table("photo_notes")


def test_photo_notes_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("photo_notes")}
    assert cols == {"id", "photo_id", "note_text", "x", "y", "x2", "y2", "created_at", "updated_at"}


def test_photo_notes_photo_id_fk(engine):
    fks = inspect(engine).get_foreign_keys("photo_notes")
    assert any(
        fk["referred_table"] == "photos" and "photo_id" in fk["constrained_columns"]
        for fk in fks
    )


# --- photos new columns / indexes ---

def test_photos_source_indexed(engine):
    idxs = inspect(engine).get_indexes("photos")
    assert any("source" in idx["column_names"] for idx in idxs)


def test_photos_photo_type_indexed(engine):
    idxs = inspect(engine).get_indexes("photos")
    assert any("photo_type" in idx["column_names"] for idx in idxs)


def test_photos_location_id_indexed(engine):
    idxs = inspect(engine).get_indexes("photos")
    assert any("location_id" in idx["column_names"] for idx in idxs)


def test_photos_location_id_fk(engine):
    fks = inspect(engine).get_foreign_keys("photos")
    assert any(
        fk["referred_table"] == "locations" and "location_id" in fk["constrained_columns"]
        for fk in fks
    )


# --- locations ---

def test_locations_table_exists(engine):
    assert inspect(engine).has_table("locations")


def test_locations_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("locations")}
    assert cols == {"id", "name", "description", "created_at", "updated_at"}


# --- growing_units ---

def test_growing_units_table_exists(engine):
    assert inspect(engine).has_table("growing_units")


def test_growing_units_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("growing_units")}
    assert cols == {
        "id", "name", "unit_type", "species", "variety", "source",
        "started_at", "notes", "current_location_id", "created_at", "updated_at",
    }


def test_growing_units_current_location_id_fk(engine):
    fks = inspect(engine).get_foreign_keys("growing_units")
    assert any(
        fk["referred_table"] == "locations" and "current_location_id" in fk["constrained_columns"]
        for fk in fks
    )


# --- photo_growing_units ---

def test_photo_growing_units_table_exists(engine):
    assert inspect(engine).has_table("photo_growing_units")


def test_photo_growing_units_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("photo_growing_units")}
    assert cols == {"photo_id", "growing_unit_id", "created_at"}


def test_photo_growing_units_photo_fk(engine):
    fks = inspect(engine).get_foreign_keys("photo_growing_units")
    assert any(
        fk["referred_table"] == "photos" and "photo_id" in fk["constrained_columns"]
        for fk in fks
    )


def test_photo_growing_units_growing_unit_fk(engine):
    fks = inspect(engine).get_foreign_keys("photo_growing_units")
    assert any(
        fk["referred_table"] == "growing_units" and "growing_unit_id" in fk["constrained_columns"]
        for fk in fks
    )


def test_photo_growing_units_growing_unit_id_indexed(engine):
    idxs = inspect(engine).get_indexes("photo_growing_units")
    assert any("growing_unit_id" in idx["column_names"] for idx in idxs)


def test_growing_units_current_location_id_indexed(engine):
    idxs = inspect(engine).get_indexes("growing_units")
    assert any("current_location_id" in idx["column_names"] for idx in idxs)
