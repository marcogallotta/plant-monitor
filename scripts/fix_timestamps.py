#!/usr/bin/env python3
"""Scan all photos, read EXIF DateTimeOriginal, and fix captured_at where it differs.

Usage:
    python scripts/fix_timestamps.py [--apply]

Without --apply, runs as a dry run and prints what would change.
"""

import sys
from pathlib import Path
from datetime import timezone

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"

for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break

import argparse

# Single source of truth for EXIF parsing — shared with the upload path so the
# trailing-NUL handling can never diverge. Returns a datetime, the NO_OFFSET
# sentinel, or None.
from app.exif import NO_OFFSET, read_exif_captured_at


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry run)")
    args = parser.parse_args()

    from app.database import build_engine, build_session_factory
    from app.models import Photo

    engine = build_engine()
    SessionFactory = build_session_factory(engine)

    mismatch = []
    no_exif = 0
    no_offset = 0
    ok = 0

    with SessionFactory() as db:
        photos = db.query(Photo).order_by(Photo.captured_at).all()
        print(f"Scanning {len(photos)} photos…")

        for photo in photos:
            path = PHOTOS_DIR / photo.filename
            if not path.exists():
                continue

            exif_dt = read_exif_captured_at(path)
            if exif_dt is None:
                no_exif += 1
                continue
            if exif_dt is NO_OFFSET:
                no_offset += 1
                continue

            stored = photo.captured_at
            if stored.tzinfo is None:
                from datetime import timezone as tz
                stored = stored.replace(tzinfo=tz.utc)
            else:
                stored = stored.astimezone(timezone.utc)

            diff_seconds = abs((exif_dt - stored).total_seconds())
            if diff_seconds > 60:
                mismatch.append((photo, exif_dt, stored, diff_seconds))
            else:
                ok += 1

        print(f"  OK (within 60s): {ok}")
        print(f"  No EXIF:         {no_exif}")
        print(f"  No tz offset:    {no_offset}  (skipped — local wall-clock time, UTC unknown)")
        print(f"  Mismatch:        {len(mismatch)}")
        print()

        if not mismatch:
            print("Nothing to fix.")
            return

        for photo, exif_dt, stored, diff in sorted(mismatch, key=lambda x: x[0].id):
            print(f"  [{photo.id}] {photo.filename}")
            print(f"    stored:  {stored.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"    exif:    {exif_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC  (diff {diff/3600:.1f}h)")

        if not args.apply:
            print(f"\nDry run — pass --apply to write {len(mismatch)} fix(es) to the DB.")
            return

        print(f"\nApplying {len(mismatch)} fix(es)…")
        for photo, exif_dt, stored, diff in mismatch:
            photo.captured_at = exif_dt
        db.commit()
        print("Done.")


if __name__ == "__main__":
    main()
