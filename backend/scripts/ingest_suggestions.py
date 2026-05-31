#!/usr/bin/env python3
"""Ingest AI suggestion JSON into photo_ai_suggestions.

Usage:
    python scripts/ingest_suggestions.py suggestions.json
    python scripts/ingest_suggestions.py -          # read from stdin

The input is a JSON array of suggestion objects. Each object must include
a photo_id. All other fields are optional and map directly to the table columns.

Example object:
    {
        "photo_id": 42,
        "model": "claude-sonnet-4-6",
        "batch_hint": "delivery day",
        "suggested_plant_name": "Sorrel",
        "confidence": "high",
        "suggested_photo_type": "health_check",
        "suggested_labels": ["wilting", "delivery_stress"],
        "suggested_rotation": null,
        "observation": "Plant dramatically drooping over pot sides.",
        "question": null,
        "x": 0.0, "y": 0.0, "x2": 0.5, "y2": 1.0,
        "prompt_context": {"neighbours": [], "known_units": []}
    }
"""

import argparse
import json
import sys

from app.database import build_engine, build_session_factory
from app.models import GrowingUnit, Photo, PhotoAiSuggestion

VALID_STATUSES = {"pending", "accepted", "edited", "rejected", "deleted"}
VALID_CONFIDENCES = {"high", "medium", "low", None}
VALID_ROTATIONS = {0, 90, 180, 270, None}


def _validate(row, idx: int) -> list[str]:
    errors = []
    if not isinstance(row, dict):
        errors.append(f"[{idx}] row must be an object")
        return errors
    if "photo_id" not in row:
        errors.append(f"[{idx}] missing photo_id")
    if "model" not in row:
        errors.append(f"[{idx}] missing model")
    if row.get("confidence") not in VALID_CONFIDENCES:
        errors.append(f"[{idx}] invalid confidence: {row['confidence']!r}")
    if row.get("suggested_rotation") not in VALID_ROTATIONS:
        errors.append(f"[{idx}] invalid suggested_rotation: {row['suggested_rotation']!r}")
    status = row.get("status", "pending")
    if status not in VALID_STATUSES:
        errors.append(f"[{idx}] invalid status: {status!r}")
    if "suggested_labels" in row and row["suggested_labels"] is not None and not isinstance(row["suggested_labels"], list):
        errors.append(f"[{idx}] suggested_labels must be a list")
    if "suggested_options" in row and row["suggested_options"] is not None:
        if not isinstance(row["suggested_options"], list) or not all(isinstance(x, str) for x in row["suggested_options"]):
            errors.append(f"[{idx}] suggested_options must be a list of strings")
    for coord in ("x", "y", "x2", "y2"):
        val = row.get(coord)
        if val is not None and not isinstance(val, (int, float)):
            errors.append(f"[{idx}] {coord} must be a number")
        elif val is not None and not (0.0 <= val <= 1.0):
            errors.append(f"[{idx}] {coord} must be in 0..1")
    has_x2 = row.get("x2") is not None
    has_y2 = row.get("y2") is not None
    if has_x2 != has_y2:
        errors.append(f"[{idx}] x2 and y2 must be provided together")
    return errors


class IngestError(Exception):
    pass


def ingest_rows(rows: list[dict], db) -> int:
    """Insert suggestion rows into the DB. Returns the number inserted.

    Raises IngestError on validation failure or missing photo_ids.
    The caller owns the session lifecycle (commit/rollback).
    """
    if not isinstance(rows, list):
        raise IngestError("input must be a JSON array")

    all_errors = []
    for i, row in enumerate(rows):
        all_errors.extend(_validate(row, i))
    if all_errors:
        raise IngestError("\n".join(all_errors))

    photo_ids = {row["photo_id"] for row in rows}
    existing_ids = {
        pid for (pid,) in db.query(Photo.id).filter(Photo.id.in_(photo_ids)).all()
    }
    missing = photo_ids - existing_ids
    if missing:
        raise IngestError(f"photo_id(s) not found: {sorted(missing)}")

    unit_ids = {row["suggested_plant_id"] for row in rows if row.get("suggested_plant_id") is not None}
    if unit_ids:
        existing_unit_ids = {
            uid for (uid,) in db.query(GrowingUnit.id).filter(GrowingUnit.id.in_(unit_ids)).all()
        }
        missing_units = unit_ids - existing_unit_ids
        if missing_units:
            raise IngestError(f"suggested_plant_id(s) not found: {sorted(missing_units)}")

    for row in rows:
        db.add(PhotoAiSuggestion(
            photo_id=row["photo_id"],
            model=row["model"],
            batch_hint=row.get("batch_hint"),
            prompt_context=row.get("prompt_context"),
            x=row.get("x"),
            y=row.get("y"),
            x2=row.get("x2"),
            y2=row.get("y2"),
            suggested_plant_id=row.get("suggested_plant_id"),
            suggested_plant_name=row.get("suggested_plant_name"),
            suggested_photo_type=row.get("suggested_photo_type"),
            suggested_rotation=row.get("suggested_rotation"),
            suggested_labels=row.get("suggested_labels"),
            confidence=row.get("confidence"),
            question=row.get("question"),
            suggested_options=row.get("suggested_options"),
            observation=row.get("observation"),
            status=row.get("status", "pending"),
        ))

    return len(rows)


def ingest(path: str) -> None:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with open(path) as f:
            data = json.load(f)

    session_factory = build_session_factory(build_engine())
    with session_factory() as db:
        try:
            count = ingest_rows(data, db)
        except IngestError as e:
            sys.exit(f"error: {e}")
        db.commit()
        print(f"inserted {count} suggestion(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="path to JSON file, or - for stdin")
    args = parser.parse_args()
    ingest(args.file)
