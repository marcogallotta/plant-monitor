import pytest
from sqlalchemy import inspect


def test_photos_table_exists(engine):
    assert inspect(engine).has_table("photos")


def test_photos_columns(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("photos")}
    assert cols == {"id", "filename", "captured_at", "storage_path", "metadata_path", "created_at"}


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
    assert cols == {"id", "photo_id", "note_text", "x", "y", "created_at", "updated_at"}


def test_photo_notes_photo_id_fk(engine):
    fks = inspect(engine).get_foreign_keys("photo_notes")
    assert any(
        fk["referred_table"] == "photos" and "photo_id" in fk["constrained_columns"]
        for fk in fks
    )
