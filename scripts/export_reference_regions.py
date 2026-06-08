#!/usr/bin/env python3
"""Export the human-verified region tags on the canonical reference frame from
the DB (photo_notes) into scripts/reference_regions.json — the fixture that
frame_registration.py / sun_shade.py / sun_hours.py read.

The DB is the source of truth; this regenerates the snapshot so re-marking in the
dashboard reaches the scripts in one command (closes the manual-snapshot gap).

Two region kinds come out:
  - "regions": plant tags (note has growing_unit_id) -> {unit_id, x,y,x2,y2}
  - "controls": non-plant FIXED reference patches (text-only notes: wall, road,
    railing, sign, glass...) -> {label, x,y,x2,y2}. These are the negative
    controls that estimate per-frame global reference error WITHOUT touching the
    plant cohort (so a real broad sun-sweep is not erased). See sun_hours.py.

Only notes with a full rectangle (x2/y2 set) are exported; point notes are skipped.

Run inside the backend container (it has app.database + the ./scripts mount):
    docker compose run --rm backend python scripts/export_reference_regions.py
"""
import os, sys, json
sys.path.insert(0, "/app")  # backend app package inside the container
from sqlalchemy import select
from app.database import _get_session_factory
from app.models import Photo, PhotoNote

REFERENCE_FRAME = "2026-06-07T130010Z.jpg"
OUT = os.path.join(os.path.dirname(__file__), "reference_regions.json")


def main():
    Session = _get_session_factory()
    with Session() as db:
        photo = db.execute(
            select(Photo).where(Photo.storage_path.like(f"%{REFERENCE_FRAME}%"))
        ).scalars().first()
        if photo is None:
            sys.exit(f"reference frame {REFERENCE_FRAME} not found in DB")
        notes = db.execute(
            select(PhotoNote).where(PhotoNote.photo_id == photo.id).order_by(PhotoNote.id)
        ).scalars().all()

    regions, controls, skipped = [], [], 0
    for n in notes:
        if n.x2 is None or n.y2 is None:        # point note, not a box
            skipped += 1
            continue
        box = {"x": n.x, "y": n.y, "x2": n.x2, "y2": n.y2}
        if n.growing_unit_id is not None:
            regions.append({"unit_id": n.growing_unit_id, **box})
        else:
            controls.append({"label": (n.note_text or "").strip(), **box})

    out = {
        "_comment": (
            f"Snapshot of the human-verified region tags on the canonical reference frame "
            f"{REFERENCE_FRAME} (photo_notes). DB is the source of truth; regenerate with "
            f"scripts/export_reference_regions.py. Corners may be in any order (use min/max). "
            f"unit_id is NOT unique (a unit can have multiple regions). 'controls' are fixed "
            f"non-plant patches used as negative controls for the per-frame global residual."
        ),
        "reference_frame": REFERENCE_FRAME,
        "regions": regions,
        "controls": controls,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT}: {len(regions)} plant regions, {len(controls)} controls "
          f"({skipped} point notes skipped)")
    for c in controls:
        print(f"  control: {c['label']}")


if __name__ == "__main__":
    main()
